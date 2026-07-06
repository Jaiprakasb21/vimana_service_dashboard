import csv
import io
import json
from contextlib import closing
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pymysql


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(r"C:\Users\prakash.b\Documents\monthly_counts_script\proddb_counts _script\prodDbConfig.json")
CLIENT_CODES = [
    "VIMA7410",
    "VIMA6636",
    "VIMA1526",
    "VIMA7257",
    "VIMA5914",
    "VIMA6295",
    "VIMA7626",
]

SERVICES = {
    "esign": {"label": "ESIGN_SERVICE", "dbName": "klpl_esign"},
    "location": {"label": "VERI5_LOCATION", "dbName": "kl_verification"},
}
DEFAULT_SERVICE = "esign"
LOCATION_VERIFICATION_TYPE = "LOCATION"


def load_db_config(db_name):
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "host": config["host"],
        "port": config["port"],
        "user": config["user"],
        "password": config["password"],
        "database": db_name,
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def get_connection(db_name):
    return pymysql.connect(**load_db_config(db_name))


def parse_iso_date(value: str, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"Invalid {field_name}. Expected YYYY-MM-DD.") from exc


def normalize_client_code(value: str) -> str:
    if not value or value == "ALL":
        return "ALL"
    if value not in CLIENT_CODES:
        raise ValueError("Unsupported client code.")
    return value


def build_in_clause(items):
    placeholders = ",".join(["%s"] * len(items))
    return f"({placeholders})"


def build_where(from_date: date, to_date: date, client_code: str):
    where_sql = f"""
        WHERE et.client_code IN {build_in_clause(CLIENT_CODES)}
          AND FROM_UNIXTIME(CAST(et.timestamp AS UNSIGNED) / 1000, '%%Y-%%m-%%d-%%H:%%i:%%s') >= %s
          AND FROM_UNIXTIME(CAST(et.timestamp AS UNSIGNED) / 1000, '%%Y-%%m-%%d-%%H:%%i:%%s') <= %s
    """
    params = list(CLIENT_CODES)
    params.extend([
        f"{from_date.isoformat()}-00:00:00",
        f"{to_date.isoformat()}-23:59:59",
    ])
    if client_code != "ALL":
        where_sql += " AND et.client_code = %s"
        params.append(client_code)
    return where_sql, params


def fetch_grouped_rows(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where(from_date, to_date, client_code)
    sql = f"""
        SELECT
            et.client_code AS clientCode,
            SUM(CASE WHEN aeres.status = 1 THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN aeres.status = 0 THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM esign_transaction et
        INNER JOIN esp_response aeres
            ON et.esign_txn_id = aeres.esign_txn_id
        {where_sql}
        GROUP BY et.client_code
        ORDER BY totalCount DESC, et.client_code ASC
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    normalized_rows = [coerce_counts(row) for row in rows]
    return merge_missing_clients(normalized_rows, client_code)


def fetch_summary(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where(from_date, to_date, client_code)
    sql = f"""
        SELECT
            SUM(CASE WHEN aeres.status = 1 THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN aeres.status = 0 THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM esign_transaction et
        INNER JOIN esp_response aeres
            ON et.esign_txn_id = aeres.esign_txn_id
        {where_sql}
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return coerce_counts(row or {})


def fetch_trend(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where(from_date, to_date, client_code)
    sql = f"""
        SELECT
            DATE(FROM_UNIXTIME(CAST(et.timestamp AS UNSIGNED) / 1000)) AS bucketDate,
            SUM(CASE WHEN aeres.status = 1 THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN aeres.status = 0 THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM esign_transaction et
        INNER JOIN esp_response aeres
            ON et.esign_txn_id = aeres.esign_txn_id
        {where_sql}
        GROUP BY bucketDate
        ORDER BY bucketDate ASC
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        raw_rows = cursor.fetchall()
    by_date = {row["bucketDate"]: coerce_counts(row) for row in raw_rows}
    output = []
    current = from_date
    while current <= to_date:
        row = by_date.get(current, {"successCount": 0, "failureCount": 0, "totalCount": 0})
        output.append({
            "label": current.strftime("%b %d"),
            "date": current.isoformat(),
            "successCount": int(row.get("successCount", 0)),
            "failureCount": int(row.get("failureCount", 0)),
            "totalCount": int(row.get("totalCount", 0)),
        })
        current += timedelta(days=1)
    return output


def fetch_failure_reasons(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where(from_date, to_date, client_code)
    sql = f"""
        SELECT
            COALESCE(NULLIF(TRIM(dm.failure_reason), ''), 'Not specified') AS reason,
            COUNT(*) AS reasonCount
        FROM esign_transaction et
        INNER JOIN esp_response aeres
            ON et.esign_txn_id = aeres.esign_txn_id
        INNER JOIN doc_metadata dm
            ON et.client_request_id = dm.client_request_id
        {where_sql}
          AND aeres.status = 0
        GROUP BY reason
        ORDER BY reasonCount DESC
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    return [{"reason": row["reason"], "count": int(row["reasonCount"])} for row in rows]


def fetch_total_for_range(connection, start_date: date, end_date: date, client_code: str):
    summary = fetch_summary(connection, start_date, end_date, client_code)
    return int(summary["totalCount"])


def fetch_tiles(connection, client_code: str):
    today = date.today()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return {
        "today": fetch_total_for_range(connection, today, today, client_code),
        "yesterday": fetch_total_for_range(connection, yesterday, yesterday, client_code),
        "monthToDate": fetch_total_for_range(connection, month_start, today, client_code),
        "lastMonth": fetch_total_for_range(connection, last_month_start, last_month_end, client_code),
    }


def build_where_location(from_date: date, to_date: date, client_code: str):
    where_sql = f"""
        WHERE client_code IN {build_in_clause(CLIENT_CODES)}
          AND verification_type = %s
          AND created_on >= %s
          AND created_on <= %s
    """
    params = list(CLIENT_CODES)
    params.extend([
        LOCATION_VERIFICATION_TYPE,
        f"{from_date.isoformat()} 00:00:00",
        f"{to_date.isoformat()} 23:59:59",
    ])
    if client_code != "ALL":
        where_sql += " AND client_code = %s"
        params.append(client_code)
    return where_sql, params


def fetch_grouped_rows_location(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where_location(from_date, to_date, client_code)
    sql = f"""
        SELECT
            client_code AS clientCode,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM user_txn
        {where_sql}
        GROUP BY client_code
        ORDER BY totalCount DESC, client_code ASC
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    normalized_rows = [coerce_counts(row) for row in rows]
    return merge_missing_clients(normalized_rows, client_code)


def fetch_summary_location(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where_location(from_date, to_date, client_code)
    sql = f"""
        SELECT
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM user_txn
        {where_sql}
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return coerce_counts(row or {})


def fetch_trend_location(connection, from_date: date, to_date: date, client_code: str):
    where_sql, params = build_where_location(from_date, to_date, client_code)
    sql = f"""
        SELECT
            DATE(created_on) AS bucketDate,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successCount,
            SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failureCount,
            COUNT(*) AS totalCount
        FROM user_txn
        {where_sql}
        GROUP BY bucketDate
        ORDER BY bucketDate ASC
    """
    with closing(connection.cursor()) as cursor:
        cursor.execute(sql, params)
        raw_rows = cursor.fetchall()
    by_date = {row["bucketDate"]: coerce_counts(row) for row in raw_rows}
    output = []
    current = from_date
    while current <= to_date:
        row = by_date.get(current, {"successCount": 0, "failureCount": 0, "totalCount": 0})
        output.append({
            "label": current.strftime("%b %d"),
            "date": current.isoformat(),
            "successCount": int(row.get("successCount", 0)),
            "failureCount": int(row.get("failureCount", 0)),
            "totalCount": int(row.get("totalCount", 0)),
        })
        current += timedelta(days=1)
    return output


def fetch_total_for_range_location(connection, start_date: date, end_date: date, client_code: str):
    summary = fetch_summary_location(connection, start_date, end_date, client_code)
    return int(summary["totalCount"])


def fetch_tiles_location(connection, client_code: str):
    today = date.today()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return {
        "today": fetch_total_for_range_location(connection, today, today, client_code),
        "yesterday": fetch_total_for_range_location(connection, yesterday, yesterday, client_code),
        "monthToDate": fetch_total_for_range_location(connection, month_start, today, client_code),
        "lastMonth": fetch_total_for_range_location(connection, last_month_start, last_month_end, client_code),
    }


def coerce_counts(row):
    return {
        "clientCode": row.get("clientCode"),
        "successCount": int(row.get("successCount") or 0),
        "failureCount": int(row.get("failureCount") or 0),
        "totalCount": int(row.get("totalCount") or 0),
    }


def merge_missing_clients(rows, client_code: str):
    if client_code == "ALL":
      target_codes = CLIENT_CODES
    else:
      target_codes = [client_code]
    row_map = {row["clientCode"]: row for row in rows if row.get("clientCode")}
    merged = []
    for code in target_codes:
        merged.append(row_map.get(code, {
            "clientCode": code,
            "successCount": 0,
            "failureCount": 0,
            "totalCount": 0,
        }))
    merged.sort(key=lambda row: (-row["totalCount"], row["clientCode"]))
    return merged


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self.serve_file("index.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return self.serve_file("styles.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self.serve_file("app.js", "application/javascript; charset=utf-8")
        if path == "/api/clients":
            return self.handle_clients()
        if path == "/api/dashboard":
            return self.handle_dashboard(parsed.query)
        if path == "/api/export.csv":
            return self.handle_export(parsed.query)
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def serve_file(self, name, content_type):
        file_path = BASE_DIR / name
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_clients(self):
        self.send_json({"clients": CLIENT_CODES})

    def handle_dashboard(self, query_string):
        try:
            filters = self.parse_filters(query_string)
            service = filters["service"]
            db_name = SERVICES[service]["dbName"]
            with closing(get_connection(db_name)) as connection:
                if service == "location":
                    rows = fetch_grouped_rows_location(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    summary = fetch_summary_location(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    trend = fetch_trend_location(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    tiles = fetch_tiles_location(connection, filters["client_code"])
                    failure_reasons = []
                else:
                    rows = fetch_grouped_rows(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    summary = fetch_summary(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    trend = fetch_trend(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                    tiles = fetch_tiles(connection, filters["client_code"])
                    failure_reasons = fetch_failure_reasons(connection, filters["from_date"], filters["to_date"], filters["client_code"])
            self.send_json({
                "filters": {
                    "from": filters["from_date"].isoformat(),
                    "to": filters["to_date"].isoformat(),
                    "clientCode": filters["client_code"],
                    "service": service,
                },
                "summary": summary,
                "clients": rows,
                "trend": trend,
                "tiles": tiles,
                "failureReasons": failure_reasons,
            })
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"Database error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_export(self, query_string):
        try:
            filters = self.parse_filters(query_string)
            service = filters["service"]
            db_name = SERVICES[service]["dbName"]
            with closing(get_connection(db_name)) as connection:
                if service == "location":
                    rows = fetch_grouped_rows_location(connection, filters["from_date"], filters["to_date"], filters["client_code"])
                else:
                    rows = fetch_grouped_rows(connection, filters["from_date"], filters["to_date"], filters["client_code"])
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["Client Code", "Success Count", "Failure Count", "Total Count"])
            for row in rows:
                writer.writerow([
                    row["clientCode"],
                    row["successCount"],
                    row["failureCount"],
                    row["totalCount"],
                ])
            payload = buffer.getvalue().encode("utf-8")
            service_slug = service.replace("_", "-")
            filename = f"{service_slug}-dashboard-{filters['client_code'].lower()}-{filters['from_date']}-to-{filters['to_date']}.csv"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"error": f"Database error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def parse_filters(self, query_string):
        params = parse_qs(query_string)
        from_value = params.get("from", [""])[0]
        to_value = params.get("to", [""])[0]
        client_value = params.get("clientCode", ["ALL"])[0]
        service_value = params.get("service", [DEFAULT_SERVICE])[0]
        if service_value not in SERVICES:
            raise ValueError("Unsupported service.")
        if not from_value or not to_value:
            raise ValueError("Both from and to dates are required.")
        from_date = parse_iso_date(from_value, "from")
        to_date = parse_iso_date(to_value, "to")
        if from_date > to_date:
            raise ValueError("From date must be on or before to date.")
        return {
            "from_date": from_date,
            "to_date": to_date,
            "client_code": normalize_client_code(client_value),
            "service": service_value,
        }

    def send_json(self, payload, status=HTTPStatus.OK):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8010), DashboardHandler)
    print("Serving ESIGN_SERVICE dashboard at http://127.0.0.1:8010")
    server.serve_forever()


if __name__ == "__main__":
    main()

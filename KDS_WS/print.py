from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import win32print
import win32ui
from datetime import datetime
from threading import Thread

PORT = 1000  # local print server port

# ------------------- Print Function -------------------
def print_ticket(ticket):
    try:
        printer_name = win32print.GetDefaultPrinter()
        if not printer_name:
            print("⚠️ No default printer found")
            return

        # --- Printer DC ---
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        pdc.StartDoc("KOT Ticket")
        pdc.StartPage()

        # --- Margins ---
        y_start = 0
        x_start = 20
        right_padding = 10

        # --- Fonts ---
        header_font = win32ui.CreateFont({"name": "Consolas", "height": 40, "weight": 700})
        subheader_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 700})
        item_font = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 700})
        footer_font = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 400})

        line_height_header = 55
        line_height_subheader = 40
        line_height_item = 30

        printable_width = pdc.GetDeviceCaps(8)  # HORZRES

        # --- Header ---
        bill_type = ticket.get("bill_type", "N/A")
        bill_type = "Table" if bill_type == "Table billing" else bill_type
        table_no = ticket.get("table_no", "")
        kot_no = ticket.get("kot_no", "")
        bill_no = ticket.get("bill_no", "")

        header_text = f"{bill_type} : {table_no}" if bill_type == "Table" else bill_type
        pdc.SelectObject(header_font)
        width = pdc.GetTextExtent(header_text)[0]
        center_x = (printable_width - width) // 2
        pdc.TextOut(center_x, y_start, header_text)
        y_start += line_height_header

        pdc.SelectObject(subheader_font)
        subheader_text = f"Bill:{bill_no} | KOT:{kot_no}"
        pdc.TextOut(x_start, y_start, subheader_text)
        y_start += line_height_subheader

        # --- Date/Time ---
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        pdc.TextOut(x_start, y_start, f"Date: {date_str}    Time: {time_str}")
        y_start += line_height_subheader

        # --- Items Header ---
        pdc.TextOut(x_start, y_start, "ITEM")
        qty_width = pdc.GetTextExtent("QTY")[0]
        qty_x = printable_width - qty_width - right_padding
        pdc.TextOut(qty_x, y_start, "QTY")
        y_start += line_height_item

        # --- Items ---
        pdc.SelectObject(item_font)
        items = ticket.get("items", [])
        for item in items:
            name = str(item.get("name", ""))
            qty = str(item.get("qty", ""))
            # Wrap long names
            max_width = qty_x - x_start - 5
            while pdc.GetTextExtent(name)[0] > max_width:
                # Find break point
                for i in range(len(name)-1, 0, -1):
                    if pdc.GetTextExtent(name[:i])[0] <= max_width:
                        pdc.TextOut(x_start, y_start, name[:i])
                        name = name[i:].lstrip()
                        y_start += line_height_item
                        break
            pdc.TextOut(x_start, y_start, name)
            pdc.TextOut(qty_x, y_start, qty)
            y_start += line_height_item

        # --- Footer ---
        pdc.TextOut(x_start, y_start, "-" * 50)
        y_start += line_height_item

        stwd = ticket.get("stwd", "")
        if stwd:
            pdc.TextOut(x_start, y_start, f"Steward: {stwd}  Items: {len(items)}")
            y_start += line_height_item

        pdc.SelectObject(footer_font)
        footer_text = "KDS PRINT"
        width = pdc.GetTextExtent(footer_text)[0]
        center_x = (printable_width - width) // 2
        pdc.TextOut(center_x, y_start, footer_text)

        # --- End Print ---
        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()
        print(f"✅ Printed ticket #{kot_no}")

    except Exception as e:
        print("❌ Print error:", e)

# ------------------- HTTP Handler -------------------
class Handler(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_headers()
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            ticket = data.get("ticket")
            if ticket:
                print_ticket(ticket)
            self.send_response(200)
            self._set_headers()
            self.end_headers()
            self.wfile.write(b"Printed")
        except Exception as e:
            self.send_response(500)
            self._set_headers()
            self.end_headers()
            self.wfile.write(f"Error: {e}".encode())

# ------------------- Run Server -------------------
if __name__ == "__main__":
    def run_print_server():
        server = HTTPServer(("0.0.0.0", PORT), Handler)
        print(f"✅ Local print server running at http://0.0.0.0:{PORT}")
        server.serve_forever()

    Thread(target=run_print_server, daemon=True).start()
    print("Press Ctrl+C to stop the server")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n❌ Server stopped manually")

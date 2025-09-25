from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import win32print
import win32ui
from datetime import datetime
import asyncio


PORT = 1000  # any free port

# ------------------- Print Function -------------------
def print_ticket(ticket):
    try:
        printer_name = win32print.GetDefaultPrinter()
        if not printer_name:
            print("⚠️ No default printer found")
            return

        # --- Fetch all ticket fields safely ---
        cashier = ticket.get("cashier", "N/A")
        kot_no = ticket.get("kot_no", "N/A")
        table_no = ticket.get("table_no", "N/A")
        bill_no = ticket.get("bill_no", "N/A")
        stwd = ticket.get("stwd", "")
        items = ticket.get("items", []) or []
        order_type = ticket.get("order_type", "N/A")
        bill_type = ticket.get("bill_type", "N/A")
        bill_type = "Table" if bill_type == "Table billing" else bill_type

        # --- Printer DC ---
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        pdc.StartDoc("KOT Ticket")
        pdc.StartPage()

        # --- Margins ---
        y_start = 0
        x_start = 0
        right_padding = 0

        # --- Fonts ---
        header_font = win32ui.CreateFont({"name": "Consolas", "height": 40, "weight": 700})
        subheader_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 700})
        item_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 700})
        end_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 400})

        line_height_header = 55
        line_height_subheader = 37
        line_height_item = 30
        line_height = 15

        printable_width = pdc.GetDeviceCaps(8)  # HORZRES

        # --- Header: Bill, KOT, Table ---
        pdc.SelectObject(header_font)
        if bill_type == "Table" :
            table_text = f"{bill_type} : {table_no}"
        else :
            table_text = f"{bill_type}"
        table_width = pdc.GetTextExtent(table_text)[0]
        center_x = (printable_width - table_width) // 2
        pdc.TextOut(center_x, y_start, table_text)
        y_start += line_height_header
        pdc.SelectObject(subheader_font)
        header_text = f"Bill:{bill_no} | KOT:{kot_no}"
        pdc.TextOut(x_start, y_start, header_text)
        y_start += line_height_item
        pdc.SelectObject(header_font)
        pdc.TextOut(x_start, y_start, "-" * 80)
        y_start += line_height_subheader

        # --- Order Type, Date, Time ---
        from datetime import datetime
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        order_info = f"Date: {date_str}           Time: {time_str}"
        pdc.SelectObject(subheader_font)
        pdc.TextOut(x_start, y_start, order_info)
        y_start += line_height_subheader

        # --- Items Header ---
        pdc.TextOut(x_start, y_start, "ITEM")
        qty_width = pdc.GetTextExtent("QTY")[0]
        qty_x = printable_width - qty_width - right_padding
        pdc.TextOut(qty_x, y_start, "QTY")
        y_start += line_height_item
        pdc.TextOut(x_start, y_start, "-" * 80)
        y_start += line_height_item

        # --- Items ---
        total = 0
        count = 0
        pdc.SelectObject(item_font)
        for item in items:
            count += 1
            total += 1
            name = str(item.get("name", ""))
            qty = str(item.get("qty", ""))

            # Maximum width for the name
            qty_width = pdc.GetTextExtent(qty)[0]
            qty_x = printable_width - qty_width - right_padding
            max_name_width = qty_x - x_start - 30  # leave some padding

            # Check if splitting is needed
            if pdc.GetTextExtent(name)[0] > max_name_width:
                # Split name into multiple lines
                words = name.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = f"{current_line} {word}".strip()
                    if pdc.GetTextExtent(test_line)[0] <= max_name_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
            else:
                lines = [name]

            # Print each line
            for i, line in enumerate(lines):
                text_x = x_start
                if i == 0:
                    # Print item index only on first line
                    pdc.TextOut(text_x, y_start, f"{count}.")
                    text_x += pdc.GetTextExtent(f"{count}. ")[0]
                # Print the item name
                pdc.TextOut(text_x, y_start, line)
                # Print quantity only on the last line
                if i == len(lines) - 1:
                    pdc.TextOut(qty_x, y_start, qty)
                y_start += line_height_item

        # --- Footer ---
        pdc.TextOut(x_start, y_start, "-" * 80)
        y_start += line_height_item

        if bill_type in ["Take Away", "Delivery"] :
            pdc.TextOut(x_start, y_start, f"Cashier: {cashier}")
            pdc.TextOut(qty_x - 100, y_start, f"Items: {total}")

        else:
            if stwd:
                pdc.TextOut(x_start, y_start, f"Steward: {stwd}")
                pdc.TextOut(qty_x - 100, y_start, f"Items: {total}")

        pdc.SelectObject(end_font)
        y_start += line_height_item
        end_text = f"KDS PRINT"
        end_width = pdc.GetTextExtent(table_text)[0]
        end_x = (printable_width - end_width) // 2
        pdc.TextOut(end_x, y_start, end_text)

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

# ------------------- Start HTTP print server in background -------------------
if __name__ == "__main__":
    from threading import Thread

    # Start local HTTP print server in the background
    def run_print_server():
        server = HTTPServer(("0.0.0.0", PORT), Handler)
        print(f"✅ Local print server running at http://0.0.0.0:{PORT}")
        server.serve_forever()

    Thread(target=run_print_server, daemon=True).start()

    # Keep main thread alive
    print("Press Ctrl+C to stop the server")
    try:
        import time
        while True:
            time.sleep(1)  # idle without CPU spike
  # busy wait, or you can use time.sleep(1) to reduce CPU usage
    except KeyboardInterrupt:
        print("\n❌ Server stopped manually")

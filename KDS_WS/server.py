
import asyncio
import json
import websockets
import pyodbc
from http.server import SimpleHTTPRequestHandler, HTTPServer
from threading import Thread
import time
import win32print
import win32ui

# ------------------- DB Connection -------------------
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-NKDVK7U;"
    "DATABASE=synopos-cp;"
    "UID=posgst11;"
    "PWD=hello213;"
)

# ------------------- Globals -------------------
STATUS_MAP = ["Pending", "Ready", "Delivered"]

# Original site clients
clients = set()

# KDS_DEL site clients
clients_kds_del = set()

# Track KDS name for each connected client
client_kds_map = {}

# ------------------- NEW: In-Memory Cache -------------------
cached_tickets = []
cached_summary = []
cached_kds_tickets = {}

# ------------------- Prints ---------------------
def print_ticket(ticket):
    try:
        printer_name = win32print.GetDefaultPrinter()
        if not printer_name:
            print("⚠️ No default printer found")
            return

        # --- Fetch all ticket fields safely ---
        kot_no = ticket.get("kot_no", "N/A")
        table_no = ticket.get("table_no", "N/A")
        bill_no = ticket.get("bill_no", "N/A")
        stwd = ticket.get("stwd", "")
        items = ticket.get("items", []) or []

        # --- Printer DC ---
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        pdc.StartDoc("KOT Ticket")
        pdc.StartPage()

        # --- Margins ---
        y_start = 0
        x_start = 30
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
        table_text = f"TABLE : {table_no}"
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

        order_info = f"Date: {date_str}    Time: {time_str}"
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
        pdc.SelectObject(item_font)
        for item in items:
            total += 1
            name = str(item.get("name", ""))
            qty = str(item.get("qty", ""))

            # Adjust name if too long
            qty_width = pdc.GetTextExtent(qty)[0]
            qty_x = printable_width - qty_width - right_padding
            while pdc.GetTextExtent(name)[0] + x_start + 5 >= qty_x:
                name = name[:-1]

            pdc.TextOut(x_start, y_start, name)
            pdc.TextOut(qty_x, y_start, qty)
            y_start += line_height_item

        # --- Footer ---
        pdc.TextOut(x_start, y_start, "-" * 80)
        y_start += line_height_item

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

# ------------------- ORIGINAL FETCH TICKETS -------------------
def fetch_tickets():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Data @KDS ='NONE'")
        rows = cursor.fetchall()
        tickets = {}
        for row in rows:
            kot_no = row.KOT_NO
            bill_no = getattr(row, "BillNO", None)
            table_name = getattr(row, "TableName", None)
            created_on = getattr(row, "CreatedOn", None)
            comments = getattr(row, "comments", "") or ""
            cancel_type = getattr(row, "Cancel_Type", 0)
            order_type = getattr(row, "bill_type", "")
            i_code = getattr(row, "I_Code", None)
            i_name = getattr(row, "I_Name", "")
            qty = getattr(row, "Qty", 0)
            item_status_idx = int(getattr(row, "order_status", 0))
            item_status = STATUS_MAP[item_status_idx]
            ack_status = getattr(row, "ack_status", 0)

            if kot_no not in tickets:
                tickets[kot_no] = {
                    "kot_no": kot_no,
                    "bill_no": bill_no,
                    "table_no": table_name,
                    "order_type": order_type,
                    "created_on": str(created_on) if created_on else "",
                    "order_status": item_status,
                    "Comments": comments,
                    "Cancelled": str(cancel_type) == "1",
                    "items": []
                }

            tickets[kot_no]["items"].append({
                "i_code": str(i_code) if i_code else "",
                "name": i_name,
                "qty": qty,
                "status": item_status,
                "ack_status": ack_status
            })
        conn.close()
        return list(tickets.values())
    except Exception as e:
        print("❌ DB Error:", e)
        return []

# ------------------- ORIGINAL FOOD SUMMARY -------------------
def fetch_food_summary():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Summary @KDS='NONE'")
        rows = cursor.fetchall()
        summary = [{"name": getattr(row, "I_Name", ""), "qty": getattr(row, "Qty", 0)} for row in rows]
        conn.close()
        return summary
    except Exception as e:
        print("❌ Food Summary DB Error:", e)
        return []

# ------------------- CACHE REFRESH FUNCTIONS -------------------
def refresh_cache():
    global cached_tickets, cached_summary
    cached_tickets = fetch_tickets()
    cached_summary = fetch_food_summary()

def refresh_kds_cache(kds_name="NONE"):
    global cached_kds_tickets
    cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)

# ------------------- Async Background Refresh -------------------
def async_refresh_kds(kds_name):
    """Refresh KDS_DEL tickets in a background thread."""
    def worker():
        try:
            cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)
        except Exception as e:
            print(f"❌ Async refresh error for {kds_name}:", e)
    Thread(target=worker, daemon=True).start()

# ------------------- ORIGINAL UPDATE ITEM STATUS -------------------
def update_item_status(kot_no, bill_no=None, i_code=None, cancel=False):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        if cancel:
            cursor.execute("UPDATE tbl_TempKot SET Cancel_Type = 1 WHERE KOT_NO = ?", kot_no)
        else:
            if kot_no is None or bill_no is None or i_code is None:
                conn.close()
                return
            cursor.execute("EXEC dbo.USP_Update_KDS ?, ?, ?", kot_no, str(i_code), bill_no)
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ Update Error:", e)

# ------------------- ORIGINAL ACK TICKET -------------------
def ack_ticket(kot_no, bill_no=None):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Accept_KDS @KDS='NONE', @KOT_NO=?", kot_no)
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ ACK Error:", e)

# ------------------- ORIGINAL BROADCAST -------------------
async def broadcast_tickets():
    for client in clients.copy():
        try:
            await client.send(json.dumps({"tickets": cached_tickets, "summary": cached_summary}))
        except:
            clients.discard(client)

# ------------------- ORIGINAL WEBSOCKET -------------------
async def ws_handler(websocket):
    clients.add(websocket)
    print("✅ Client connected")
    try:
        await websocket.send(json.dumps({"tickets": cached_tickets, "summary": cached_summary}))
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                data = json.loads(message)
                action = data.get("action")
                if action == "toggle_item":
                    update_item_status(data.get("kot_no"), data.get("bill_no"), data.get("i_code"))
                    refresh_cache()
                elif action == "cancel_ticket":
                    update_item_status(data.get("kot_no"), cancel=True)
                    refresh_cache()
                elif action == "ack_ticket":
                    ack_ticket(data.get("kot_no"), data.get("bill_no"))
                    refresh_cache()
                await broadcast_tickets()
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
    except websockets.exceptions.ConnectionClosed:
        print("❌ Client disconnected")
    finally:
        clients.discard(websocket)

# ------------------- KDS_DEL FETCH TICKETS -------------------
def fetch_kds_del_tickets(kds_name="NONE"):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_GET_KDS_DEL_Data @KDS = ?", kds_name)
        rows = cursor.fetchall()
        print(f"Fetched {len(rows)} rows from KDS_DEL")  # debug

        tickets = {}
        for row in rows:
            kot_no = getattr(row, "KOT_NO", None)
            bill_no = getattr(row, "BillNO", None)
            table_name = getattr(row, "TableName", "")
            i_code = getattr(row, "I_Code", "")
            i_name = getattr(row, "I_Name", "")
            qty = getattr(row, "Qty", 0)
            steward = getattr(row, "stwd", "")
            ready_date = getattr(row, "ready_date", "") 
            bill_type = getattr(row, "bill_type", "")

            ready_status = getattr(row, "ready_status")
            if ready_status is None:
                ready_status = 0
            else:
                ready_status = int(ready_status)

            order_status_idx = getattr(row, "order_status", 0)
            order_status_text = STATUS_MAP[order_status_idx]

            if kot_no is None or bill_no is None:
                print(f"Skipping row with missing KOT_NO or BillNO: {row}")
                continue

            if kot_no not in tickets:
                tickets[kot_no] = {
                    "kot_no": kot_no,
                    "bill_no": bill_no,
                    "table_no": table_name,
                    "ready_date": str(ready_date) if ready_date else "",
                    "stwd": steward,
                    "items": [],
                    "ticketstatus": 0,
                    "order_type": "",
                    "bill_type": bill_type
                }

            tickets[kot_no]["items"].append({
                "i_code": str(i_code),
                "name": i_name,
                "qty": qty,
                "ready_status": ready_status,
                "status": order_status_text
            })

            ready_items = sum(1 for it in tickets[kot_no]["items"] if it["ready_status"] == 1)
            total_items = len(tickets[kot_no]["items"])

            if ready_items == total_items and total_items > 0:
                tickets[kot_no]["ticketstatus"] = 2
            elif ready_items > 0:
                tickets[kot_no]["ticketstatus"] = 1
            else:
                tickets[kot_no]["ticketstatus"] = 0

        conn.close()
        print(f"KDS_DEL tickets prepared: {len(tickets)}")
        return list(tickets.values())

    except Exception as e:
        print("❌ KDS_DEL DB Error:", e)
        return []

# ------------------- KDS_DEL UPDATE -------------------
def update_kds_del_ticket(kot_no, bill_no, items):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        for item in items:
            i_code = item["i_code"]
            cursor.execute("EXEC dbo.USP_UPDATE_KDS_DEL ?, ?, ?", kot_no, i_code, bill_no)
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ KDS_DEL Update Error:", e)

# ------------------- KDS_DEL BROADCAST -------------------
async def broadcast_kds_del_tickets():
    for client in clients_kds_del.copy():
        try:
            kds_name = client_kds_map.get(client, "NONE")
            if kds_name not in cached_kds_tickets:
                async_refresh_kds(kds_name)
            await client.send(json.dumps({"tickets": cached_kds_tickets.get(kds_name, [])}))
        except:
            clients_kds_del.discard(client)

# ------------------- KDS_DEL WEBSOCKET -------------------
async def ws_kds_del_handler(websocket):
    clients_kds_del.add(websocket)
    client_kds_map[websocket] = "NONE"
    print("✅ KDS_DEL client connected")

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                data = json.loads(message)
                action = data.get("action")

                # ---------- Initialize KDS ----------
                if action == "init_kds":
                    kds_name = data.get("kds_name", "NONE")
                    client_kds_map[websocket] = kds_name

                    # Ensure cache exists immediately
                    if kds_name not in cached_kds_tickets:
                        print(f"🔄 First load: fetching tickets for KDS '{kds_name}'")
                        cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)

                    # Send tickets to this client immediately
                    tickets = cached_kds_tickets.get(kds_name, [])
                    await websocket.send(json.dumps({"tickets": tickets}))

                    # Refresh cache asynchronously for future updates
                    async_refresh_kds(kds_name)
                    continue

                # ---------- Toggle Ticket ----------
                if action == "toggle_ticket":
                    update_kds_del_ticket(
                        data.get("kot_no"),
                        data.get("bill_no"),
                        data.get("items")
                    )
                    kds_name = client_kds_map.get(websocket, "NONE")

                    # Refresh cache for this KDS
                    cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)

                    # Broadcast to all KDS clients
                    await broadcast_kds_del_tickets()
                    continue

            except asyncio.TimeoutError:
                # keep loop alive
                await asyncio.sleep(0.01)

    except websockets.exceptions.ConnectionClosed:
        print("❌ KDS_DEL client disconnected")

    finally:
        clients_kds_del.discard(websocket)
        client_kds_map.pop(websocket, None)


# ------------------- HTTP SERVER -------------------
def run_http():
    httpd = HTTPServer(("0.0.0.0", 9090), SimpleHTTPRequestHandler)
    print("✅ HTTP server running at http://0.0.0.0:9090")
    httpd.serve_forever()

# ------------------- SQL LISTENER -------------------
def sql_listener(loop):
    while True:
        try:
            conn = pyodbc.connect(CONN_STR, timeout=60)
            cursor = conn.cursor()
            print("🔔 Listening for trigger-based SQL notifications...")
            while True:
                cursor.execute("""
                    WAITFOR (
                        RECEIVE TOP(1)
                            conversation_handle,
                            message_type_name,
                            CAST(message_body AS NVARCHAR(MAX))
                        FROM KDS_TriggerQueue
                    ), TIMEOUT 10000;
                """)
                row = cursor.fetchone()
                if row:
                    conversation_handle, message_type, message_body = row
                    if message_type == "KDS_TriggerMessage":
                        print(f"🔔 KOT Change: {message_body}")
                        refresh_cache()
                        for kds_name in cached_kds_tickets.keys():
                            async_refresh_kds(kds_name)
                        loop.call_soon_threadsafe(lambda: asyncio.create_task(broadcast_tickets()))
                        loop.call_soon_threadsafe(lambda: asyncio.create_task(broadcast_kds_del_tickets()))
                    cursor.execute("END CONVERSATION ?", conversation_handle)
                    conn.commit()
        except Exception as e:
            print("❌ SQL Listener Error:", e)
            try: conn.close()
            except: pass
            time.sleep(5)

# ------------------- MAIN -------------------
async def main():
    refresh_cache()  # preload tickets for first client
    Thread(target=run_http, daemon=True).start()
    print("Testing DB connection...")
    print(f"Original site rows: {len(cached_tickets)}")
    print(f"KDS_DEL rows: {len(fetch_kds_del_tickets())}")
    loop = asyncio.get_running_loop()
    Thread(target=sql_listener, args=(loop,), daemon=True).start()
    async with websockets.serve(ws_handler, "0.0.0.0", 9999), \
               websockets.serve(ws_kds_del_handler, "0.0.0.0", 9998):
        print("✅ WebSocket servers running at ws://0.0.0.0:9999 and ws://0.0.0.0:9998")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
  
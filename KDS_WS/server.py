
import asyncio
import json
import logging
import websockets
import pyodbc
from http.server import SimpleHTTPRequestHandler, HTTPServer
from threading import Thread
import time
import win32print
import win32ui
import config


# ------------------- DB Connection -------------------
def get_db_connection():
    try:
        return pyodbc.connect(config.DB_CONN_STR)
    except Exception as e:
        logging.error(f"DB connection failed: {e}")
        return None

CONN_STR = config.DB_CONN_STR



# ------------------- Globals -------------------
STATUS_MAP = ["Pending", "Ready", "Delivered"]

# Original site clients
clients = set()

# KDS_DEL site clients
clients_kds_del = set()

# ------------------- Per-KDS Cache -------------------
cached_kds_main = {}          # kds_name -> {"tickets": [...], "summary": [...]}

# Track KDS name for each connected client
client_kds_map = {}

# ------------------- NEW: In-Memory Cache -------------------
cached_tickets = []
cached_summary = []
cached_kds_tickets = {}

# ------------------- Prints ---------------------
import asyncio

async def send_print(client, ticket):
    """Send a direct print command to the client."""
    try:
        await client.send(json.dumps({
            "action": "print_ticket",
            "ticket": ticket
        }))
        print(f"➡️ Print command sent for KOT {ticket.get('kot_no')}")
    except Exception as e:
        print("❌ Failed to send print command:", e)


# def print_ticket(ticket):
#     try:
#         printer_name = win32print.GetDefaultPrinter()
#         if not printer_name:
#             print("⚠️ No default printer found")
#             return

#         # --- Fetch all ticket fields safely ---
        
#         kot_no = ticket.get("kot_no", "N/A")
#         table_no = ticket.get("table_no", "N/A")
#         bill_no = ticket.get("bill_no", "N/A")
#         stwd = ticket.get("stwd", "")
#         items = ticket.get("items", []) or []
#         order_type = ticket.get("order_type", "N/A")
#         bill_type = ticket.get("bill_type", "N/A")
#         bill_type = "Table" if bill_type == "Table billing" else bill_type
#         # --- Printer DC ---
#         pdc = win32ui.CreateDC()
#         pdc.CreatePrinterDC(printer_name)
#         pdc.StartDoc("KOT Ticket")
#         pdc.StartPage()

#         # --- Margins ---
#         y_start = 0
#         x_start = 30
#         right_padding = 0

#         # --- Fonts ---
#         header_font = win32ui.CreateFont({"name": "Consolas", "height": 40, "weight": 700})
#         subheader_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 700})
#         item_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 700})
#         end_font = win32ui.CreateFont({"name": "Consolas", "height": 30, "weight": 400})

#         line_height_header = 55
#         line_height_subheader = 37
#         line_height_item = 30
#         line_height = 15

#         printable_width = pdc.GetDeviceCaps(8)  # HORZRES

#         # --- Header: Bill, KOT, Table ---
#         pdc.SelectObject(header_font)
#         if bill_type == "Table" :
#             table_text = f"{bill_type} : {table_no}"
#         else :
#             table_text = f"{bill_type}"
#         table_width = pdc.GetTextExtent(table_text)[0]
#         center_x = (printable_width - table_width) // 2
#         pdc.TextOut(center_x, y_start, table_text)
#         y_start += line_height_header
#         pdc.SelectObject(subheader_font)
#         header_text = f"Bill:{bill_no} | KOT:{kot_no}"
#         pdc.TextOut(x_start, y_start, header_text)
#         y_start += line_height_item
#         pdc.SelectObject(header_font)
#         pdc.TextOut(x_start, y_start, "-" * 80)
#         y_start += line_height_subheader

#         # --- Order Type, Date, Time ---
#         from datetime import datetime
#         now = datetime.now()
#         date_str = now.strftime("%Y-%m-%d")
#         time_str = now.strftime("%H:%M:%S")

#         order_info = f"Date: {date_str}    Time: {time_str}"
#         pdc.SelectObject(subheader_font)
#         pdc.TextOut(x_start, y_start, order_info)
#         y_start += line_height_subheader

#         # --- Items Header ---
#         pdc.TextOut(x_start, y_start, "ITEM")
#         qty_width = pdc.GetTextExtent("QTY")[0]
#         qty_x = printable_width - qty_width - right_padding
#         pdc.TextOut(qty_x, y_start, "QTY")
#         y_start += line_height_item
#         pdc.TextOut(x_start, y_start, "-" * 80)
#         y_start += line_height_item

#         # --- Items ---
#         total = 0
#         pdc.SelectObject(item_font)
#         for item in items:
#             total += 1
#             name = str(item.get("name", ""))
#             qty = str(item.get("qty", ""))

#             # Adjust name if too long
#             qty_width = pdc.GetTextExtent(qty)[0]
#             qty_x = printable_width - qty_width - right_padding
#             while pdc.GetTextExtent(name)[0] + x_start + 5 >= qty_x:
#                 name = name[:-1]

#             pdc.TextOut(x_start, y_start, name)
#             pdc.TextOut(qty_x, y_start, qty)
#             y_start += line_height_item

#         # --- Footer ---
#         pdc.TextOut(x_start, y_start, "-" * 80)
#         y_start += line_height_item

#         if stwd:
#             pdc.TextOut(x_start, y_start, f"Steward: {stwd}")
#             pdc.TextOut(qty_x - 100, y_start, f"Items: {total}")

#         pdc.SelectObject(end_font)
#         y_start += line_height_item
#         end_text = f"KDS PRINT"
#         end_width = pdc.GetTextExtent(table_text)[0]
#         end_x = (printable_width - end_width) // 2
#         pdc.TextOut(end_x, y_start, end_text)

#         # --- End Print ---
#         pdc.EndPage()
#         pdc.EndDoc()
#         pdc.DeleteDC()

#         print(f"✅ Printed ticket #{kot_no}")

#     except Exception as e:
#         print("❌ Print error:", e)

# ------------------- ORIGINAL FETCH TICKETS -------------------
def fetch_tickets(kds_name="NONE"):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Data @KDS =?", kds_name)
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
def fetch_food_summary(kds_name="NONE"):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Summary @KDS = ?", kds_name)
        rows = cursor.fetchall()
        summary = [{"name": getattr(row, "I_Name", ""), "qty": getattr(row, "Qty", 0)} for row in rows]
        conn.close()
        return summary
    except Exception as e:
        print("❌ Food Summary DB Error:", e)
        return []

# ------------------- CACHE REFRESH FUNCTIONS -------------------
def refresh_main_kds_cache(kds_name="NONE"):
    """Fetch tickets and summary for a specific KDS and store in cache."""
    try:
        tickets = fetch_tickets(kds_name)      # your existing function
        summary = fetch_food_summary(kds_name) # your existing function
        cached_kds_main[kds_name] = {"tickets": tickets, "summary": summary}
    except Exception as e:
        print(f"❌ Failed to refresh main KDS cache for {kds_name}: {e}")

def async_refresh_main_kds(kds_name="NONE"):
    Thread(target=refresh_main_kds_cache, args=(kds_name,), daemon=True).start()


def safe_refresh_cache(kds_name="NONE"):
    try:
        refresh_cache(kds_name)
    except Exception as e:
        print("❌ Cache refresh failed:", e)

def refresh_cache(kds_name="NONE"):
    global cached_tickets, cached_summary
    cached_tickets = fetch_tickets(kds_name)
    cached_summary = fetch_food_summary(kds_name)

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
            cursor.execute("EXEC dbo.USP_Accept_kds ?, ?, ?", kot_no, str(i_code), bill_no)
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ Update Error:", e)

# ------------------- ORIGINAL ACK TICKET -------------------
def ack_ticket(kot_no, bill_no=None, items=None):
    try:
        if not items:
            print("❌ ACK Error: No items provided for ticket", kot_no)
            return

        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        for item in items:
            i_code = item.get("i_code")
            if not i_code:
                continue
            cursor.execute("EXEC dbo.USP_Accept_kds ?, ?, ?", kot_no, str(i_code), bill_no)

        conn.commit()
        conn.close()
        print(f"✅ ACK completed for ticket {kot_no} with {len(items)} items")

    except Exception as e:
        print("❌ ACK Error:", e)



# ------------------- ORIGINAL BROADCAST -------------------
async def broadcast_main_kds(kds_name=None):
    """Send tickets+summary only to clients of the given KDS (or all if kds_name=None)."""
    for client in clients.copy():
        try:
            client_kds = client_kds_map.get(client, "NONE")
            if kds_name and client_kds != kds_name:
                continue
            data = cached_kds_main.get(client_kds, {"tickets": [], "summary": []})
            await client.send(json.dumps(data))
        except:
            clients.discard(client)



async def ws_handler(websocket):
    clients.add(websocket)
    print("✅ KDS client connected")
    try:
        kds_name = client_kds_map.get(websocket, "NONE")

        # Send cached data immediately (if exists), else empty
        data = cached_kds_main.get(kds_name, {"tickets": [], "summary": []})
        await websocket.send(json.dumps(data))

        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                data = json.loads(message)
                action = data.get("action")

                if action == "init_kds":
                    kds_name = data.get("kds_name", "NONE")
                    client_kds_map[websocket] = kds_name
                    refresh_main_kds_cache(kds_name)
                    await broadcast_main_kds(kds_name)
                    print(f"Client initialized with KDS: {kds_name}")

                elif action == "toggle_item":
                    update_item_status(data.get("kot_no"), data.get("bill_no"), data.get("i_code"))
                    async_refresh_main_kds(client_kds_map.get(websocket, "NONE"))
                    await broadcast_main_kds(client_kds_map.get(websocket, "NONE"))

                elif action == "cancel_ticket":
                    update_item_status(data.get("kot_no"), cancel=True)
                    async_refresh_main_kds(client_kds_map.get(websocket, "NONE"))
                    await broadcast_main_kds(client_kds_map.get(websocket, "NONE"))

                elif action == "ack_ticket":
                    ack_ticket(data.get("kot_no"), data.get("bill_no"), data.get("items"))
                    async_refresh_main_kds(client_kds_map.get(websocket, "NONE"))
                    await broadcast_main_kds(client_kds_map.get(websocket, "NONE"))

            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)

    except websockets.exceptions.ConnectionClosed:
        print("❌ KDS client disconnected")
    finally:
        clients.discard(websocket)
        client_kds_map.pop(websocket, None)

# ------------------- KDS_DEL FETCH TICKETS -------------------
def fetch_kds_del_tickets(kds_name="NONE"):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_GET_KDS_DEL_Data @KDS = ?", kds_name)
        rows = cursor.fetchall()

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
            cashier = getattr(row,"cashier", "")


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
                    "bill_type": bill_type,
                    "cashier": cashier
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
        # Send empty tickets first
        await websocket.send(json.dumps({"tickets": cached_kds_tickets.get("NONE", [])}))

        while True:
            message = await websocket.recv()
            data = json.loads(message)
            action = data.get("action")

            # ---------- Initialize KDS ----------
            if action == "init_kds":
                kds_name = data.get("kds_name", "NONE")
                client_kds_map[websocket] = kds_name
                safe_refresh_cache(kds_name)
                cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)
                print(f"Client initialized with KDS: {kds_name}")
                # Send to this client immediately
                await websocket.send(json.dumps({"tickets": cached_kds_tickets[kds_name]}))
                continue

            # ---------- Initialize Recall Screen ----------
            elif action == "init_kds_recall":
                kds_name = data.get("kds_name", "NONE")
                client_kds_map[websocket] = kds_name
                delivered = fetch_delivered_tickets(kds_name)
                await websocket.send(json.dumps({"delivered_tickets": delivered}))
                print(f"Recall tickets for {kds_name}: {len(delivered)}")
                continue

            # ---------- Recall Item ----------
            elif action == "recall_item":
                kot_no = data.get("kot_no")
                i_code = data.get("i_code")
                bill_no = data.get("bill_no")
                recall_item(kot_no, i_code, bill_no)
                # Refresh cache only once
                safe_refresh_cache()
                # Update main KDS clients
                await broadcast_main_kds()

                # Update this recall screen with fresh delivered tickets
                kds_name = client_kds_map.get(websocket, "NONE")
                delivered = fetch_delivered_tickets(kds_name)
                await websocket.send(json.dumps({"delivered_tickets": delivered}))
                continue

            # ---------- Toggle Ticket ----------
            elif action == "toggle_ticket":
                kds_name = client_kds_map.get(websocket, "NONE")
                update_kds_del_ticket(
                    data.get("kot_no"),
                    data.get("bill_no"),
                    data.get("items")
                )

                # Refresh KDS cache only once after update
                cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)
                delivered_tickets = fetch_delivered_tickets(kds_name)
                safe_refresh_cache()

                # Optional: Print when toggling ON
                try:
                    should_print = data.get("print", True)
                    if should_print:
                        kot_to_print = str(data.get("kot_no"))
                        for t in cached_kds_tickets.get(kds_name, []):
                            if str(t.get("kot_no")) == kot_to_print:
                                ready_items = [item for item in t["items"] if int(item.get("ready_status", 0)) == 1]
                                if ready_items:
                                    t_copy = {**t, "items": ready_items}
                                    asyncio.create_task(send_print(websocket, t_copy))
                                    # print_ticket(t_copy)
                                break
                except Exception as e:
                    print("❌ Print-on-toggle error:", e)
                    
                                # Optional: Print when toggling ON
                # try:
                #     kot_to_print = str(data.get("kot_no"))
                #     for t in cached_kds_tickets.get(kds_name, []):
                #         if str(t.get("kot_no")) == kot_to_print:
                #             # Only include items that are ready
                #             ready_items = [item for item in t["items"] if int(item.get("ready_status", 0)) == 1]

                #             # Set print flag for client
                #             if ready_items and data.get("print", True):
                #                 t["print"] = True
                #                 t["items"] = ready_items  # only ready items sent for printing
                #             else:
                #                 t["print"] = False
                #             break
                # except Exception as e:
                #     print("❌ Print-on-toggle error:", e)

                # Broadcast to all KDS_DEL clients
                await broadcast_kds_del_tickets()
                await websocket.send(json.dumps({"delivered_tickets": delivered_tickets}))

                continue

    except websockets.exceptions.ConnectionClosed:
        print("❌ KDS_DEL client disconnected")
    finally:
        clients_kds_del.discard(websocket)
        client_kds_map.pop(websocket, None)

# ------------------- KDS_Delivered FETCH TICKETS -------------------
def fetch_delivered_tickets(kds_name="NONE"):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Delivered_Data @KDS = ?", kds_name)
        rows = cursor.fetchall()
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
        conn.close()
        return list(tickets.values())
    except Exception as e:
        print("❌ Delivered Tickets Error:", e)
        return []

def recall_item(kot_no, i_code, bill_no):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Recall_KDS_DEL_Data ?, ?, ?", kot_no, i_code, bill_no)
        conn.commit()
        conn.close()
        print(f"✅ Recalled item {i_code} from KOT {kot_no}")
    except Exception as e:
        print("❌ Recall Error:", e)


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
            print("🔔 SQL listener connected")
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
                        for kds_name in cached_kds_main.keys():
                            cached_kds_main[kds_name] = {
                            "tickets": fetch_tickets(kds_name),
                            "summary": fetch_food_summary(kds_name)
                        }
                        safe_refresh_cache()
                        for kds_name in list(cached_kds_tickets.keys()):
                            cached_kds_tickets[kds_name] = fetch_kds_del_tickets(kds_name)
                        loop.call_soon_threadsafe(asyncio.create_task, broadcast_main_kds())
                        loop.call_soon_threadsafe(asyncio.create_task, broadcast_kds_del_tickets())
                    cursor.execute("END CONVERSATION ?", conversation_handle)
                    conn.commit()
        except Exception as e:
            print("❌ SQL Listener Error. Retrying in 5s:", e)
            time.sleep(5)  # retry DB connection

# ------------------- MAIN -------------------
async def main():
    cached_tickets.clear()
    cached_summary.clear()
    cached_kds_tickets.clear()
    safe_refresh_cache() # preload tickets for first client
    Thread(target=run_http, daemon=True).start()
    print("Testing DB connection...")
    print(f"KDS tickets: {len(cached_tickets)}")
    print(f"KDS_DEL tickets: {len(fetch_kds_del_tickets())}")
    loop = asyncio.get_running_loop()
    Thread(target=sql_listener, args=(loop,), daemon=True).start()
    async with websockets.serve(ws_handler, "0.0.0.0", 9999), \
               websockets.serve(ws_kds_del_handler, "0.0.0.0", 9998):
        print("✅ WebSocket servers running at ws://0.0.0.0:9999 and ws://0.0.0.0:9998")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
  
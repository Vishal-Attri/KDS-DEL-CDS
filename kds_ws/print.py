import win32print
import win32ui
import textwrap

def print_ticket(ticket):
    """
    Print a KOT ticket:
    - Left-aligned from printer margin
    - Item names left, quantities right
    - Wraps long names
    - Error handling included
    """
    try:
        printer_name = win32print.GetDefaultPrinter()
        if not printer_name:
            print("⚠️ No default printer found")
            return

        kot_no = ticket.get("kot_no", "N/A")
        table_no = ticket.get("table_no", "N/A")
        items = ticket.get("items", []) or []

        # --- Prepare ticket lines ---
        lines = []
        lines.append(f"KOT #{kot_no}      Table {table_no}")
        lines.append("-" * 50)

        name_width = 36  # max chars for name
        qty_width = 5    # max chars for quantity

        for item in items:
            name = str(item.get("name", ""))
            qty = str(item.get("qty", ""))
            # Wrap long names
            wrapped = textwrap.wrap(name, width=name_width)
            for i, line in enumerate(wrapped):
                if i == len(wrapped) - 1:
                    # Last line: include qty in right-aligned column
                    lines.append(f"{line:<{name_width}}{qty:>{qty_width}}")
                else:
                    lines.append(line)

        lines.append("-" * 50)
        lines.append("\n")

        # --- Print ---
        hprinter = win32print.OpenPrinter(printer_name)
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        pdc.StartDoc("KOT Ticket")
        pdc.StartPage()

        font = win32ui.CreateFont({
            "name": "Courier New",
            "height": 30,
            "weight": 700
        })
        pdc.SelectObject(font)

        x_start = 0  # start from left margin
        y_start = 10
        line_height = 28

        for i, line in enumerate(lines):
            # Truncate line if too long
            safe_line = line
            max_width = pdc.GetDeviceCaps(8) - 10  # horizontal printable pixels minus margin
            while pdc.GetTextExtent(safe_line)[0] > max_width:
                safe_line = safe_line[:-1]
            pdc.TextOut(x_start, y_start + i * line_height, safe_line)

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()

        print(f"✅ Printed ticket #{kot_no}")

    except Exception as e:
        print("❌ Print error:", e)

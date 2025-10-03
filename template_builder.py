#!/usr/bin/env python3
"""
STR PDF Template Builder - Tkinter GUI version
Interactive interface with draggable boxes and corner handles
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import pdfplumber

# Pre-populated bounding boxes based on STR form analysis
# Boxes cover VALUE ONLY (not field labels)
# Note: MAKLUMAT ANAK uses table extraction, MAKLUMAT WARIS uses header-based extraction
INITIAL_BOXES = {
    # MAKLUMAT PEMOHON - Left Column (from user's template.json)
    "nama": {"x": 47, "y": 86, "width": 466, "height": 15},
    "no_mykad": {"x": 73, "y": 113, "width": 194, "height": 16},
    "umur": {"x": 53, "y": 133, "width": 217, "height": 16},
    "jantina": {"x": 62, "y": 153, "width": 209, "height": 17},
    "no_telefon_rumah": {"x": 104, "y": 174, "width": 167, "height": 13},
    "no_telefon_bimbit": {"x": 100, "y": 194, "width": 167, "height": 14},
    "pekerjaan": {"x": 67, "y": 215, "width": 203, "height": 17},
    "pendapatan_kasar": {"x": 104, "y": 234, "width": 162, "height": 16},
    "status_perkahwinan": {"x": 106, "y": 276, "width": 153, "height": 15},
    "tarikh_perkahwinan": {"x": 104, "y": 304, "width": 155, "height": 20},
    "tarikh_cerai_kematian": {"x": 104, "y": 333, "width": 155, "height": 20},

    # MAKLUMAT PEMOHON - Right Column (placed at TOP for easy rearrangement)
    "alamat_surat": {"x": 20, "y": 20, "width": 100, "height": 16},
    "poskod": {"x": 130, "y": 20, "width": 60, "height": 16},
    "bandar_daerah": {"x": 200, "y": 20, "width": 80, "height": 16},
    "negeri": {"x": 290, "y": 20, "width": 80, "height": 16},
    "nama_bank": {"x": 380, "y": 20, "width": 120, "height": 20},
    "no_akaun_bank": {"x": 510, "y": 20, "width": 100, "height": 16},
    "alamat_emel": {"x": 620, "y": 20, "width": 120, "height": 16},
}

class BoundingBox:
    """Represents a single bounding box with handles"""

    HANDLE_SIZE = 6
    HANDLE_COLOR = "blue"
    BOX_COLOR_NORMAL = "green"
    BOX_COLOR_SELECTED = "red"
    BOX_WIDTH = 2

    def __init__(self, canvas, name, x, y, width, height, scale=1.0):
        self.canvas = canvas
        self.name = name
        self.scale = scale

        # Store original PDF coordinates
        self.pdf_x = x
        self.pdf_y = y
        self.pdf_width = width
        self.pdf_height = height

        # Display coordinates (scaled)
        self.x = int(x * scale)
        self.y = int(y * scale)
        self.width = int(width * scale)
        self.height = int(height * scale)

        self.selected = False
        self.canvas_items = []
        self.handles = []

        self.draw()

    def draw(self):
        """Draw the box and handles on canvas"""
        # Clear existing items
        for item in self.canvas_items:
            self.canvas.delete(item)
        self.canvas_items.clear()

        # Draw rectangle
        color = self.BOX_COLOR_SELECTED if self.selected else self.BOX_COLOR_NORMAL
        rect = self.canvas.create_rectangle(
            self.x, self.y, self.x + self.width, self.y + self.height,
            outline=color, width=self.BOX_WIDTH, tags=f"box_{self.name}"
        )
        self.canvas_items.append(rect)

        # Draw label
        label = self.canvas.create_text(
            self.x + 2, self.y - 8,
            text=self.name, anchor="sw",
            fill=color, font=("Arial", 8, "bold"),
            tags=f"label_{self.name}"
        )
        self.canvas_items.append(label)

        # Draw corner handles if selected
        self.handles.clear()
        if self.selected:
            corners = [
                (self.x, self.y, "nw"),  # Top-left
                (self.x + self.width, self.y, "ne"),  # Top-right
                (self.x, self.y + self.height, "sw"),  # Bottom-left
                (self.x + self.width, self.y + self.height, "se"),  # Bottom-right
            ]

            for cx, cy, corner_type in corners:
                handle = self.canvas.create_rectangle(
                    cx - self.HANDLE_SIZE // 2, cy - self.HANDLE_SIZE // 2,
                    cx + self.HANDLE_SIZE // 2, cy + self.HANDLE_SIZE // 2,
                    fill=self.HANDLE_COLOR, outline="white",
                    tags=f"handle_{self.name}_{corner_type}"
                )
                self.canvas_items.append(handle)
                self.handles.append((handle, corner_type, cx, cy))

    def contains_point(self, px, py):
        """Check if point is inside the box"""
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def get_handle_at_point(self, px, py):
        """Check if point is on a handle, return corner type if yes"""
        if not self.selected:
            return None

        for _, corner_type, cx, cy in self.handles:
            if abs(px - cx) <= self.HANDLE_SIZE and abs(py - cy) <= self.HANDLE_SIZE:
                return corner_type
        return None

    def move_to(self, x, y):
        """Move box to new position"""
        self.x = x
        self.y = y
        self.update_pdf_coords()
        self.draw()

    def resize_corner(self, corner_type, new_x, new_y):
        """Resize box by dragging a corner"""
        if corner_type == "nw":  # Top-left
            self.width = max(10, self.width + (self.x - new_x))
            self.height = max(10, self.height + (self.y - new_y))
            self.x = new_x
            self.y = new_y
        elif corner_type == "ne":  # Top-right
            self.width = max(10, new_x - self.x)
            self.height = max(10, self.height + (self.y - new_y))
            self.y = new_y
        elif corner_type == "sw":  # Bottom-left
            self.width = max(10, self.width + (self.x - new_x))
            self.height = max(10, new_y - self.y)
            self.x = new_x
        elif corner_type == "se":  # Bottom-right
            self.width = max(10, new_x - self.x)
            self.height = max(10, new_y - self.y)

        self.update_pdf_coords()
        self.draw()

    def update_pdf_coords(self):
        """Update PDF coordinates from display coordinates"""
        self.pdf_x = int(self.x / self.scale)
        self.pdf_y = int(self.y / self.scale)
        self.pdf_width = int(self.width / self.scale)
        self.pdf_height = int(self.height / self.scale)

    def set_selected(self, selected):
        """Set selection state"""
        self.selected = selected
        self.draw()

    def get_pdf_box(self):
        """Return box in PDF coordinates"""
        return {
            "x": self.pdf_x,
            "y": self.pdf_y,
            "width": self.pdf_width,
            "height": self.pdf_height
        }


class TemplateBuilder:
    def update_window_title(self):
        """Update window title to show current template"""
        template_name = "With Pasangan" if self.template_type.get() == "with_pasangan" else "Without Pasangan"
        self.root.title(f"STR Template Builder - {template_name}")

    def get_current_template_file(self):
        """Get the current template file path"""
        return self.template_files[self.template_type.get()]

    def switch_template(self):
        """Switch to a different template"""
        # Update window title
        self.update_window_title()

        # Reload boxes from new template
        self.refresh_boxes()

        print(f"✓ Switched to {self.get_current_template_file()}")

    def refresh_boxes(self):
        """Refresh bounding boxes from current template file"""
        # Load boxes from current template
        self.initial_boxes = self.load_initial_boxes()

        # Clear existing boxes
        for box in self.boxes.values():
            for item in box.canvas_items:
                self.canvas.delete(item)

        self.boxes.clear()
        self.box_listbox.delete(0, tk.END)
        self.selected_box = None

        # Recreate boxes
        self.create_boxes()

        print(f"✓ Refreshed {len(self.boxes)} boxes from {self.get_current_template_file()}")

    def load_initial_boxes(self):
        """Load bounding boxes from current template file if it exists, otherwise use fallback"""
        from pathlib import Path

        template_path = Path(self.get_current_template_file())

        if template_path.exists():
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                    boxes = template.get('fields', {})
                    print(f"✓ Loaded {len(boxes)} boxes from {template_path}")
                    return boxes
            except Exception as e:
                print(f"⚠ Warning: Could not load {template_path}: {e}")
                print(f"  Using fallback boxes instead")
        else:
            print(f"⚠ {template_path} not found, using fallback boxes")

        # Fallback to hardcoded INITIAL_BOXES
        return INITIAL_BOXES.copy()

    def load_current_pdf(self):
        """Load and display the current PDF"""
        self.pdf_path = str(self.pdf_files[self.current_pdf_index])
        print(f"Loading PDF {self.current_pdf_index + 1}/{len(self.pdf_files)}: {self.pdf_files[self.current_pdf_index].name}")

        with pdfplumber.open(self.pdf_path) as pdf:
            page = pdf.pages[0]
            # Convert to image
            pil_image = page.to_image(resolution=150).original
            self.pdf_image = pil_image

        # Resize PDF image for display
        display_size = (self.canvas_width, self.canvas_height)
        self.display_image = self.pdf_image.resize(display_size, Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(self.display_image)

        # Update canvas image if canvas exists
        if hasattr(self, 'canvas'):
            if self.canvas_image_id:
                self.canvas.delete(self.canvas_image_id)
            self.canvas_image_id = self.canvas.create_image(0, 0, image=self.photo_image, anchor="nw", tags="pdf_image")
            self.canvas.tag_lower("pdf_image")  # Send to back

            # Redraw all boxes
            for box in self.boxes.values():
                box.draw()

            # Update PDF counter label if it exists
            if hasattr(self, 'pdf_counter_label'):
                self.pdf_counter_label.config(
                    text=f"PDF {self.current_pdf_index + 1} of {len(self.pdf_files)}: {self.pdf_files[self.current_pdf_index].name}"
                )

    def navigate_pdf(self, direction):
        """Navigate to previous/next PDF"""
        new_index = self.current_pdf_index + direction
        if 0 <= new_index < len(self.pdf_files):
            self.current_pdf_index = new_index
            self.load_current_pdf()

    def __init__(self, pdf_source, output_json="template.json"):
        from pathlib import Path

        self.output_json = output_json

        # Template files mapping
        self.template_files = {
            "with_pasangan": "template_with_pasangan.json",
            "without_pasangan": "template_without_pasangan.json"
        }
        self.current_template_type = "with_pasangan"  # Track template type (before tk.StringVar)

        # Determine if pdf_source is a folder or file
        source_path = Path(pdf_source)
        if source_path.is_dir():
            # Load all PDFs from folder
            self.pdf_files = sorted(source_path.glob("*.pdf"))
            if not self.pdf_files:
                raise ValueError(f"No PDF files found in {pdf_source}")
            print(f"Found {len(self.pdf_files)} PDF files in folder")
        else:
            # Single PDF file
            self.pdf_files = [source_path]

        self.current_pdf_index = 0
        self.pdf_path = str(self.pdf_files[self.current_pdf_index])

        self.boxes = {}
        self.selected_box = None
        self.drag_data = {"box": None, "handle": None, "x": 0, "y": 0}

        # Create main window FIRST
        self.root = tk.Tk()

        # Now we can create tk.StringVar (after root window exists)
        self.template_type = tk.StringVar(value="with_pasangan")

        # Load initial boxes from template file
        self.initial_boxes = self.load_initial_boxes()

        self.update_window_title()

        # Initialize PDF display variables
        self.pdf_width = None
        self.pdf_height = None
        self.pdf_image = None
        self.display_image = None
        self.photo_image = None
        self.canvas_image_id = None

        # Load first PDF to get dimensions
        print(f"Loading initial PDF...")
        with pdfplumber.open(self.pdf_path) as pdf:
            page = pdf.pages[0]
            self.pdf_width = page.width
            self.pdf_height = page.height

        # Calculate scale to fit screen
        max_width = 1000
        max_height = 1200
        scale_w = max_width / self.pdf_width
        scale_h = max_height / self.pdf_height
        self.scale = min(scale_w, scale_h, 2.0)  # Max 2x zoom

        self.canvas_width = int(self.pdf_width * self.scale)
        self.canvas_height = int(self.pdf_height * self.scale)

        # Setup UI
        self.setup_ui()

        # Load first PDF fully (with image)
        self.load_current_pdf()
        self.create_boxes()

        print(f"\nPDF: {self.pdf_width}x{self.pdf_height}")
        print(f"Display: {self.canvas_width}x{self.canvas_height}")
        print(f"Scale: {self.scale:.2f}x")
        print(f"Loaded {len(self.boxes)} bounding boxes\n")

    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel - Canvas
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas with scrollbars
        self.canvas = tk.Canvas(
            canvas_frame,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="gray"
        )

        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        self.canvas.config(scrollregion=(0, 0, self.canvas_width, self.canvas_height))

        # Pack scrollbars and canvas
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # PDF image will be added in load_current_pdf()

        # Right panel - Controls
        control_frame = ttk.Frame(main_frame, padding=10)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Title
        title = ttk.Label(control_frame, text="STR Template Builder", font=("Arial", 14, "bold"))
        title.pack(pady=10)

        # Template Selector
        template_frame = ttk.LabelFrame(control_frame, text="Template Type", padding=10)
        template_frame.pack(pady=10, fill=tk.X)

        ttk.Radiobutton(
            template_frame,
            text="With Pasangan",
            variable=self.template_type,
            value="with_pasangan",
            command=self.switch_template
        ).pack(anchor=tk.W)

        ttk.Radiobutton(
            template_frame,
            text="Without Pasangan",
            variable=self.template_type,
            value="without_pasangan",
            command=self.switch_template
        ).pack(anchor=tk.W)

        # Refresh button
        refresh_btn = ttk.Button(template_frame, text="🔄 Refresh Boxes", command=self.refresh_boxes)
        refresh_btn.pack(pady=5, fill=tk.X)

        # PDF Navigation Controls
        if len(self.pdf_files) > 1:
            nav_frame = ttk.Frame(control_frame)
            nav_frame.pack(pady=10)

            prev_btn = ttk.Button(nav_frame, text="◀ Previous", command=lambda: self.navigate_pdf(-1))
            prev_btn.pack(side=tk.LEFT, padx=5)

            next_btn = ttk.Button(nav_frame, text="Next ▶", command=lambda: self.navigate_pdf(1))
            next_btn.pack(side=tk.LEFT, padx=5)

            self.pdf_counter_label = ttk.Label(
                control_frame,
                text=f"PDF {self.current_pdf_index + 1} of {len(self.pdf_files)}: {self.pdf_files[self.current_pdf_index].name}",
                font=("Arial", 9)
            )
            self.pdf_counter_label.pack(pady=5)

        # Box list
        list_label = ttk.Label(control_frame, text="Bounding Boxes:", font=("Arial", 10, "bold"))
        list_label.pack(pady=(10, 5))

        list_frame = ttk.Frame(control_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.box_listbox = tk.Listbox(list_frame, height=20)
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.box_listbox.yview)
        self.box_listbox.config(yscrollcommand=list_scrollbar.set)

        self.box_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind listbox selection
        self.box_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        # Buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(pady=20)

        save_btn = ttk.Button(button_frame, text="💾 Save Template", command=self.save_template)
        save_btn.pack(pady=5, fill=tk.X)

        test_btn = ttk.Button(button_frame, text="🔍 Test Extraction", command=self.test_extraction)
        test_btn.pack(pady=5, fill=tk.X)

        quit_btn = ttk.Button(button_frame, text="❌ Quit", command=self.root.quit)
        quit_btn.pack(pady=5, fill=tk.X)

        # Extraction results display
        results_label = ttk.Label(control_frame, text="Extraction Results:", font=("Arial", 10, "bold"))
        results_label.pack(pady=(10, 5))

        results_frame = ttk.Frame(control_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_text = tk.Text(results_frame, width=35, height=15, wrap=tk.WORD, font=("Courier", 9))
        results_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_text.yview)
        self.results_text.config(yscrollcommand=results_scrollbar.set)

        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Initial placeholder text
        self.results_text.insert("1.0", "Click 'Test Extraction' to see results...")
        self.results_text.config(state=tk.DISABLED)

        # Mouse bindings
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-3>", self.on_right_click)  # Right-click delete

    def create_boxes(self):
        """Create bounding boxes from initial data"""
        for name, coords in self.initial_boxes.items():
            box = BoundingBox(
                self.canvas, name,
                coords["x"], coords["y"],
                coords["width"], coords["height"],
                self.scale
            )
            self.boxes[name] = box
            self.box_listbox.insert(tk.END, name)

    def on_listbox_select(self, event):
        """Handle listbox selection"""
        selection = self.box_listbox.curselection()
        if selection:
            name = self.box_listbox.get(selection[0])
            self.select_box(self.boxes.get(name))

    def select_box(self, box):
        """Select a bounding box"""
        if self.selected_box:
            self.selected_box.set_selected(False)

        self.selected_box = box
        if box:
            box.set_selected(True)

    def get_canvas_coords(self, event_x, event_y):
        """Convert viewport coordinates to canvas coordinates (accounting for scroll)"""
        # Get scroll position (returns fraction of total scrollable area)
        x_view = self.canvas.xview()
        y_view = self.canvas.yview()

        # Calculate scroll offset in pixels
        x_offset = int(x_view[0] * self.canvas_width)
        y_offset = int(y_view[0] * self.canvas_height)

        # Add offset to event coordinates
        canvas_x = event_x + x_offset
        canvas_y = event_y + y_offset

        return canvas_x, canvas_y

    def on_mouse_down(self, event):
        """Handle mouse button press"""
        x, y = self.get_canvas_coords(event.x, event.y)

        # Check if clicking on a handle of selected box
        if self.selected_box:
            handle = self.selected_box.get_handle_at_point(x, y)
            if handle:
                self.drag_data = {"box": self.selected_box, "handle": handle, "x": x, "y": y}
                return

        # Check if clicking on any box
        for name, box in self.boxes.items():
            if box.contains_point(x, y):
                self.select_box(box)
                self.drag_data = {"box": box, "handle": None, "x": x, "y": y}
                return

        # Clicked on empty space
        self.select_box(None)

    def on_mouse_drag(self, event):
        """Handle mouse drag"""
        if not self.drag_data["box"]:
            return

        x, y = self.get_canvas_coords(event.x, event.y)
        box = self.drag_data["box"]
        handle = self.drag_data["handle"]

        if handle:
            # Resize by dragging handle
            box.resize_corner(handle, x, y)
        else:
            # Move box
            dx = x - self.drag_data["x"]
            dy = y - self.drag_data["y"]
            box.move_to(box.x + dx, box.y + dy)
            self.drag_data["x"] = x
            self.drag_data["y"] = y

    def on_mouse_up(self, event):
        """Handle mouse button release"""
        self.drag_data = {"box": None, "handle": None, "x": 0, "y": 0}

    def on_right_click(self, event):
        """Handle right-click to delete box"""
        x, y = self.get_canvas_coords(event.x, event.y)

        for name, box in list(self.boxes.items()):
            if box.contains_point(x, y):
                if messagebox.askyesno("Delete Box", f"Delete '{name}' box?"):
                    # Remove from canvas
                    for item in box.canvas_items:
                        self.canvas.delete(item)

                    # Remove from list
                    del self.boxes[name]

                    # Update listbox
                    self.box_listbox.delete(0, tk.END)
                    for box_name in self.boxes.keys():
                        self.box_listbox.insert(tk.END, box_name)

                    if self.selected_box == box:
                        self.selected_box = None
                break

    def save_template(self):
        """Save template to JSON"""
        fields = {}
        for name, box in self.boxes.items():
            fields[name] = box.get_pdf_box()

        template = {
            "pdf_dimensions": {
                "width": self.pdf_width,
                "height": self.pdf_height
            },
            "fields": fields
        }

        current_template = self.get_current_template_file()
        with open(current_template, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

        messagebox.showinfo("Success", f"✓ Template saved to {current_template}\n\n{len(fields)} boxes saved.")
        print(f"\n✓ Saved {len(fields)} boxes to {current_template}")

    def test_extraction(self):
        """Test extraction with current boxes and display results"""
        try:
            # Update results text
            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert("1.0", "Running extraction...\n\n")
            self.results_text.config(state=tk.DISABLED)
            self.root.update()  # Force UI update

            # Get ALL current boxes (no filtering)
            fields = {}
            for name, box in self.boxes.items():
                fields[name] = box.get_pdf_box()

            # Import extraction functionality
            from pathlib import Path
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from extract_str import STRExtractor

            # Create temporary template
            temp_template = {
                "pdf_dimensions": {
                    "width": self.pdf_width,
                    "height": self.pdf_height
                },
                "fields": fields
            }

            # Save to temp file
            temp_json = "_temp_template.json"
            with open(temp_json, 'w', encoding='utf-8') as f:
                json.dump(temp_template, f, indent=2, ensure_ascii=False)

            # Run extraction using new bounding box-based method
            extractor = STRExtractor(temp_json)

            with pdfplumber.open(self.pdf_path) as pdf:
                page = pdf.pages[0]

                # Extract all fields from bounding boxes
                extracted_data = {}
                pasangan_fields = {}
                waris_fields = {}

                for field_name, box in fields.items():
                    # Skip header fields
                    if field_name.endswith('_header'):
                        continue

                    text = extractor.extract_text_from_box(page, box)

                    # Group fields by prefix
                    if field_name.startswith('pasangan_'):
                        clean_name = field_name.replace('pasangan_', '')
                        pasangan_fields[clean_name] = text
                    elif field_name.startswith('waris_'):
                        clean_name = field_name.replace('waris_', '')
                        waris_fields[clean_name] = text
                    else:
                        extracted_data[field_name] = text

                # Extract MAKLUMAT ANAK table
                children = extractor.extract_anak_table(page)
                extracted_data['anak'] = children

                # Add grouped sections
                extracted_data['pasangan'] = pasangan_fields
                extracted_data['waris'] = waris_fields

            # Clean up temp file
            Path(temp_json).unlink(missing_ok=True)

            # Format and display results
            results_json = json.dumps(extracted_data, indent=2, ensure_ascii=False)

            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert("1.0", results_json)
            self.results_text.config(state=tk.DISABLED)

            print("✓ Extraction test completed")

        except Exception as e:
            error_msg = f"Error during extraction:\n\n{str(e)}"
            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert("1.0", error_msg)
            self.results_text.config(state=tk.DISABLED)
            print(f"✗ Extraction test failed: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Run the application"""
        self.root.mainloop()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Default to ./pdf folder if it exists, otherwise use a single PDF
    default_pdf_folder = Path("./pdf")
    default_pdf_file = "STR_000121131278.pdf"

    if len(sys.argv) > 1:
        pdf_source = sys.argv[1]
    elif default_pdf_folder.exists() and default_pdf_folder.is_dir():
        pdf_source = str(default_pdf_folder)
        print(f"Using PDF folder: {pdf_source}")
    else:
        pdf_source = default_pdf_file
        print(f"Using single PDF: {pdf_source}")

    builder = TemplateBuilder(pdf_source)
    builder.run()

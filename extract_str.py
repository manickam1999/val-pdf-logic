#!/usr/bin/env python3
"""
STR PDF Data Extractor - Production script
Extracts data from STR PDFs using bounding box template
"""

import json
import sys
import csv
from pathlib import Path
import pdfplumber

class STRExtractor:
    def __init__(self, template_path="template.json"):
        """Initialize extractor with template"""
        self.template_path = template_path
        self.load_template(template_path)

    def load_template(self, template_path):
        """Load template from file"""
        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)

        self.fields = template['fields']
        self.pdf_dimensions = template.get('pdf_dimensions', {})
        print(f"Loaded template with {len(self.fields)} fields from {template_path}")

    def detect_section_offset(self, page, header_field_name):
        """Detect Y-offset for a section by finding its header position

        Args:
            page: pdfplumber page object
            header_field_name: name of the header field (e.g., 'maklumat_waris_header')

        Returns:
            Y-offset in pixels (positive = shifted down, negative = shifted up)
        """
        if header_field_name not in self.fields:
            return 0

        template_box = self.fields[header_field_name]
        template_y = template_box['y']
        template_x = template_box['x']
        template_w = template_box['width']

        # Expected header text keywords
        header_keywords = {
            'maklumat_pemohon_header': ['MAKLUMAT', 'PEMOHON'],
            'maklumat_pasangan_header': ['MAKLUMAT', 'PASANGAN'],
            'maklumat_anak_header': ['MAKLUMAT', 'ANAK'],
            'maklumat_waris_header': ['MAKLUMAT', 'WARIS']
        }

        keywords = header_keywords.get(header_field_name, ['MAKLUMAT'])

        # Use larger search range for waris section (variable position due to anak section)
        search_range = 200 if header_field_name == 'maklumat_waris_header' else 50

        try:
            # Get all words in the page
            words = page.extract_words()

            # For waris header, need to find both MAKLUMAT and WARIS nearby
            if header_field_name == 'maklumat_waris_header':
                # Find all MAKLUMAT words first
                maklumat_words = []
                waris_words = []

                print(f"  DEBUG: Searching for waris header with:")
                print(f"         X range: [{template_x - 20}, {template_x + template_w + 20}]")
                print(f"         Y range: [{template_y - search_range}, {template_y + search_range}]")

                for word in words:
                    word_text = word['text'].upper()
                    word_x = word['x0']
                    word_y = word['top']

                    # Look for keywords in expected X range and expanded Y range
                    if template_x - 20 <= word_x <= template_x + template_w + 20:
                        if abs(word_y - template_y) <= search_range:
                            if 'MAKLUMAT' in word_text:
                                maklumat_words.append((word_y, word_x, word_text))
                                print(f"         Found MAKLUMAT at X={word_x:.1f}, Y={word_y:.1f}")
                            elif 'WARIS' in word_text:
                                waris_words.append((word_y, word_x, word_text))
                                print(f"         Found WARIS at X={word_x:.1f}, Y={word_y:.1f}")

                # Find MAKLUMAT and WARIS that are on the same line (within 5px vertically)
                for mak_y, mak_x, mak_text in maklumat_words:
                    for war_y, war_x, war_text in waris_words:
                        if abs(mak_y - war_y) <= 5:  # Same line
                            actual_y = mak_y
                            offset = int(actual_y - template_y)
                            print(f"  📍 {header_field_name}: Found at Y={actual_y:.1f} (template Y={template_y}), offset={offset:+d}px")
                            return offset

                # If not found, print debug info
                print(f"  ⚠️  {header_field_name}: Could not find both MAKLUMAT and WARIS nearby")
                print(f"      Found {len(maklumat_words)} MAKLUMAT words, {len(waris_words)} WARIS words in search range")
                return 0

            # For other headers, use original logic
            candidates = []
            for word in words:
                word_text = word['text'].upper()
                word_x = word['x0']
                word_y = word['top']

                # Check if word matches any keyword and is in correct X range
                if (any(kw in word_text for kw in keywords) and
                    template_x - 20 <= word_x <= template_x + template_w + 20 and
                    abs(word_y - template_y) <= search_range):
                    candidates.append((word_y, word_text))

            if candidates:
                # Use the first matching candidate (should be the header)
                actual_y = candidates[0][0]
                offset = int(actual_y - template_y)
                if offset != 0:
                    print(f"  📍 {header_field_name}: Y offset {offset:+d}px detected")
                return offset

        except Exception as e:
            print(f"  Warning: Error detecting offset for {header_field_name}: {e}")

        return 0  # No offset if header not found

    def extract_text_from_box(self, page, box, y_offset=0, tolerance=5):
        """Extract text using word filtering with section-based Y-offset and tolerance

        Args:
            page: pdfplumber page object
            box: dictionary with 'x', 'y', 'width', 'height' keys
            y_offset: Section-specific Y-offset in pixels
            tolerance: Y-axis tolerance in pixels (default: 5px, can be reduced for specific fields)

        Returns:
            Extracted text string
        """
        x, y, w, h = box['x'], box['y'], box['width'], box['height']

        # Apply section offset to Y coordinate
        y_adjusted = y + y_offset

        try:
            # Get all words on page with their coordinates
            words = page.extract_words()

            # Filter words within bounding box with Y-tolerance
            # Using tight tolerance since we already applied section offset
            field_words = [
                word for word in words
                if (x <= word['x0'] <= x + w) and
                   (y_adjusted - tolerance <= word['top'] <= y_adjusted + h + tolerance)
            ]

            if field_words:
                # Sort by position (top to bottom, left to right)
                field_words.sort(key=lambda w: (w['top'], w['x0']))
                # Join words preserving order
                text = ' '.join([w['text'] for w in field_words])
                # Clean up the text
                text = text.strip()
                # Replace multiple spaces with single space
                text = ' '.join(text.split())
                # Remove trailing punctuation (colons, semicolons, etc.)
                text = text.rstrip(':;,.')
                return text

            return ""

        except Exception as e:
            print(f"  Warning: Error extracting from box {box}: {e}")
            return ""

    def extract_anak_table(self, page):
        """Extract MAKLUMAT ANAK table using pdfplumber table detection"""
        try:
            # Extract all tables from the page
            tables = page.extract_tables()

            # Find the MAKLUMAT ANAK table (usually contains columns: NAMA, NO.MYKAD/MYKID, UMUR, STATUS)
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Check if this is the ANAK table by looking at headers
                header = table[0] if table else []
                header_text = ' '.join([str(cell or '').upper() for cell in header])

                if 'NAMA' in header_text and 'MYKAD' in header_text and 'UMUR' in header_text:
                    # Found the ANAK table
                    children = []
                    for row in table[1:]:  # Skip header row
                        if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                            continue  # Skip empty rows

                        # Extract child data (handle variable column positions)
                        child = {}
                        for i, cell in enumerate(row):
                            cell_value = str(cell).strip() if cell else ""
                            if i < len(header) and header[i]:
                                field_name = str(header[i]).strip().lower()
                                # Normalize field names
                                if 'nama' in field_name:
                                    child['nama'] = cell_value
                                elif 'mykad' in field_name or 'mykid' in field_name:
                                    child['no_mykad'] = cell_value
                                elif 'umur' in field_name:
                                    child['umur'] = cell_value
                                elif 'status' in field_name or 'hubungan' in field_name:
                                    child['status'] = cell_value

                        if child:  # Only add if we extracted something
                            children.append(child)

                    print(f"  MAKLUMAT ANAK: Extracted {len(children)} children")
                    return children

            print("  MAKLUMAT ANAK: No table found")
            return []

        except Exception as e:
            print(f"  Warning: Error extracting ANAK table: {e}")
            return []

    def extract_waris_section(self, page):
        """Extract MAKLUMAT WARIS using header-based positioning"""
        try:
            # Find the "MAKLUMAT WARIS" header text
            text_objects = page.extract_words()

            waris_header_y = None
            for word in text_objects:
                text = word['text'].upper()
                if 'MAKLUMAT' in text and 'WARIS' in text:
                    waris_header_y = word['bottom']
                    break
                elif 'WARIS' in text:
                    # Check if MAKLUMAT is nearby
                    for other_word in text_objects:
                        if abs(other_word['top'] - word['top']) < 5 and 'MAKLUMAT' in other_word['text'].upper():
                            waris_header_y = max(word['bottom'], other_word['bottom'])
                            break
                    if waris_header_y:
                        break

            if not waris_header_y:
                print("  MAKLUMAT WARIS: Header not found")
                return {}

            # Define approximate field positions relative to header
            # These are rough estimates - the actual values are extracted from text near these positions
            field_labels = {
                'hubungan': 'Hubungan',
                'no_pengenalan': 'No Pengenalan',
                'nama': 'Nama',
                'no_telefon': 'No Telefon'
            }

            waris_data = {}

            # Extract text in the WARIS section (from header to bottom of page)
            waris_bbox = (0, waris_header_y, page.width, page.height)
            waris_section = page.within_bbox(waris_bbox)
            waris_words = waris_section.extract_words()

            # For each field, find the label and extract the value after it
            for field_key, label_text in field_labels.items():
                label_found = False
                for i, word in enumerate(waris_words):
                    if label_text.upper() in word['text'].upper():
                        label_found = True
                        # Find text on the same line or slightly below (within 10px)
                        label_y = word['top']
                        label_x_end = word['x1']

                        # Collect all text after the label on the same line
                        value_parts = []
                        for other_word in waris_words:
                            # Check if word is on the same line and to the right of label
                            if abs(other_word['top'] - label_y) < 10 and other_word['x0'] > label_x_end:
                                # Skip colons
                                if other_word['text'].strip() != ':':
                                    value_parts.append(other_word['text'])

                        if value_parts:
                            waris_data[field_key] = ' '.join(value_parts).strip()
                        else:
                            waris_data[field_key] = ""
                        break

                if not label_found:
                    waris_data[field_key] = ""

            print(f"  MAKLUMAT WARIS: Extracted {len([v for v in waris_data.values() if v])} fields")
            return waris_data

        except Exception as e:
            print(f"  Warning: Error extracting WARIS section: {e}")
            return {}

    def extract_pasangan_section(self, page):
        """Extract MAKLUMAT PASANGAN using header-based positioning"""
        try:
            # Find the "MAKLUMAT PASANGAN" header text
            text_objects = page.extract_words()

            pasangan_header_y = None
            for word in text_objects:
                text = word['text'].upper()
                if 'MAKLUMAT' in text and 'PASANGAN' in text:
                    pasangan_header_y = word['bottom']
                    break
                elif 'PASANGAN' in text:
                    # Check if MAKLUMAT is nearby
                    for other_word in text_objects:
                        if abs(other_word['top'] - word['top']) < 5 and 'MAKLUMAT' in other_word['text'].upper():
                            pasangan_header_y = max(word['bottom'], other_word['bottom'])
                            break
                    if pasangan_header_y:
                        break

            if not pasangan_header_y:
                print("  MAKLUMAT PASANGAN: Header not found (applicant may not have spouse)")
                return {}

            # Find the next section header to limit extraction area
            next_section_y = page.height
            for word in text_objects:
                if word['top'] > pasangan_header_y:
                    text = word['text'].upper()
                    if 'MAKLUMAT' in text and ('ANAK' in text or 'WARIS' in text):
                        next_section_y = word['top']
                        break

            # Define field labels for PASANGAN
            field_labels = {
                'nama': 'Nama',
                'jenis_pengenalan': 'Jenis Pengenalan',
                'no_mykad': 'MyKAD',
                'negara_asal': 'Negara Asal',
                'no_telefon': 'No. Telefon',
                'jantina': 'Jantina',
                'pekerjaan': 'Pekerjaan',
                'nama_bank': 'Nama Bank Pasangan',
                'no_akaun_bank': 'No Akaun Bank Pasangan'
            }

            pasangan_data = {}

            # Extract text in the PASANGAN section (from header to next section)
            pasangan_bbox = (0, pasangan_header_y, page.width, next_section_y)
            pasangan_section = page.within_bbox(pasangan_bbox)
            pasangan_words = pasangan_section.extract_words()

            # For each field, find the label and extract the value after it
            for field_key, label_text in field_labels.items():
                label_found = False
                for i, word in enumerate(pasangan_words):
                    if label_text.upper() in word['text'].upper():
                        label_found = True
                        # Find text on the same line or slightly below (within 10px)
                        label_y = word['top']
                        label_x_end = word['x1']

                        # Collect all text after the label on the same line
                        value_parts = []
                        for other_word in pasangan_words:
                            # Check if word is on the same line and to the right of label
                            if abs(other_word['top'] - label_y) < 10 and other_word['x0'] > label_x_end:
                                # Skip colons and field labels
                                text = other_word['text'].strip()
                                if text != ':' and text.upper() not in label_text.upper():
                                    value_parts.append(text)

                        if value_parts:
                            pasangan_data[field_key] = ' '.join(value_parts).strip()
                        else:
                            pasangan_data[field_key] = ""
                        break

                if not label_found:
                    pasangan_data[field_key] = ""

            print(f"  MAKLUMAT PASANGAN: Extracted {len([v for v in pasangan_data.values() if v])} fields")
            return pasangan_data

        except Exception as e:
            print(f"  Warning: Error extracting PASANGAN section: {e}")
            return {}

    def extract_from_pdf(self, pdf_path):
        """Extract all fields from a PDF with two-stage template selection"""
        print(f"\nExtracting from: {pdf_path}")

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]  # Assuming single page form

            # STAGE 1: Quick extraction of status_perkahwinan to determine template
            print("\n  === STAGE 1: Determining template ===")
            status_perkahwinan = ""
            if 'status_perkahwinan' in self.fields:
                status_box = self.fields['status_perkahwinan']
                status_perkahwinan = self.extract_text_from_box(page, status_box).upper()
                print(f"  Status Perkahwinan: {status_perkahwinan}")

            # Determine which template to use
            if 'KAHWIN' in status_perkahwinan:
                template_to_use = "template_with_pasangan.json"
                print(f"  → Using template WITH PASANGAN")
            else:
                template_to_use = "template_without_pasangan.json"
                print(f"  → Using template WITHOUT PASANGAN")

            # STAGE 2: Reload appropriate template and extract all fields
            if template_to_use != Path(self.template_path).name:
                print(f"  Reloading template: {template_to_use}")
                self.load_template(template_to_use)

            # Verify PDF dimensions match template (optional warning)
            if self.pdf_dimensions:
                expected_w = self.pdf_dimensions.get('width')
                expected_h = self.pdf_dimensions.get('height')
                if expected_w and expected_h:
                    if abs(page.width - expected_w) > 10 or abs(page.height - expected_h) > 10:
                        print(f"  ⚠ Warning: PDF dimensions don't match template")
                        print(f"    Expected: {expected_w}x{expected_h}, Got: {page.width}x{page.height}")

            # Detect section offsets using header anchors
            print("\n  === Detecting Section Offsets ===")
            pemohon_offset = self.detect_section_offset(page, 'maklumat_pemohon_header')
            pasangan_offset = self.detect_section_offset(page, 'maklumat_pasangan_header')
            anak_offset = self.detect_section_offset(page, 'maklumat_anak_header')
            waris_offset = self.detect_section_offset(page, 'maklumat_waris_header')

            # Extract all fields from bounding boxes with section-specific offsets
            print("\n  === STAGE 2: Extracting all fields ===")
            all_fields = {}
            pasangan_fields = {}
            waris_fields = {}

            for field_name, box in self.fields.items():
                # Skip header fields (not actual data)
                if field_name.endswith('_header'):
                    continue

                # Determine section-specific offset
                if field_name.startswith('waris_'):
                    offset = waris_offset
                elif field_name.startswith('pasangan_'):
                    offset = pasangan_offset
                elif field_name.startswith('anak_'):
                    offset = anak_offset
                else:
                    # Main applicant section (MAKLUMAT PEMOHON)
                    offset = pemohon_offset

                # Determine field-specific tolerance (jantina needs tighter tolerance)
                tolerance = 3 if field_name == 'jantina' else 5

                # Extract with section offset and field-specific tolerance
                text = self.extract_text_from_box(page, box, y_offset=offset, tolerance=tolerance)

                # Group fields by prefix
                if field_name.startswith('pasangan_'):
                    clean_name = field_name.replace('pasangan_', '')
                    pasangan_fields[clean_name] = text
                    print(f"  pasangan.{clean_name}: {text[:50]}{'...' if len(text) > 50 else ''}")
                elif field_name.startswith('waris_'):
                    clean_name = field_name.replace('waris_', '')
                    waris_fields[clean_name] = text
                    print(f"  waris.{clean_name}: {text[:50]}{'...' if len(text) > 50 else ''}")
                else:
                    all_fields[field_name] = text
                    print(f"  {field_name}: {text[:50]}{'...' if len(text) > 50 else ''}")

            # Extract MAKLUMAT ANAK table
            print("\n  === MAKLUMAT ANAK (Table Extraction) ===")
            children = self.extract_anak_table(page)
            all_fields['anak'] = children

            # Add grouped sections
            all_fields['pasangan'] = pasangan_fields
            all_fields['waris'] = waris_fields

        return all_fields

    def extract_multiple(self, pdf_paths):
        """Extract from multiple PDFs"""
        all_data = []

        for pdf_path in pdf_paths:
            try:
                data = self.extract_from_pdf(pdf_path)
                data['_source_file'] = str(pdf_path)
                all_data.append(data)
            except Exception as e:
                print(f"✗ Error processing {pdf_path}: {e}")

        return all_data

    def save_to_json(self, data, output_path):
        """Save extracted data to JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Saved to {output_path}")

    def save_to_csv(self, data, output_path):
        """Save extracted data to CSV"""
        if not data:
            print("No data to save")
            return

        # Get all possible field names
        fieldnames = set()
        for record in data:
            fieldnames.update(record.keys())
        fieldnames = sorted(fieldnames)

        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"✓ Saved to {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Extract data from STR PDF files')
    parser.add_argument('pdf_files', nargs='+', help='PDF file(s) to extract from')
    parser.add_argument('-t', '--template', default='template.json',
                       help='Template JSON file (default: template.json)')
    parser.add_argument('-o', '--output', help='Output file (JSON or CSV)')
    parser.add_argument('-f', '--format', choices=['json', 'csv'], default='json',
                       help='Output format (default: json)')

    args = parser.parse_args()

    # Check template exists
    if not Path(args.template).exists():
        print(f"✗ Error: Template file '{args.template}' not found")
        print(f"  Run template_builder.py first to create the template")
        sys.exit(1)

    # Initialize extractor
    extractor = STRExtractor(args.template)

    # Process PDF(s)
    pdf_paths = [Path(p) for p in args.pdf_files]

    # Check all files exist
    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            print(f"✗ Error: PDF file '{pdf_path}' not found")
            sys.exit(1)

    # Extract data
    if len(pdf_paths) == 1:
        data = extractor.extract_from_pdf(pdf_paths[0])
        all_data = [data]
    else:
        all_data = extractor.extract_multiple(pdf_paths)

    # Save output
    if args.output:
        output_path = args.output
    else:
        # Auto-generate output filename
        if len(pdf_paths) == 1:
            base_name = pdf_paths[0].stem
        else:
            base_name = "str_extracted"
        output_path = f"{base_name}.{args.format}"

    if args.format == 'json':
        # For single file, save as object; for multiple, save as array
        save_data = all_data[0] if len(pdf_paths) == 1 else all_data
        extractor.save_to_json(save_data, output_path)
    else:
        extractor.save_to_csv(all_data, output_path)

    print(f"\n✓ Extraction complete! Processed {len(pdf_paths)} file(s)")


if __name__ == "__main__":
    main()

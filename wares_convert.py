import xml.etree.ElementTree as ET
import csv
import os
import logging
import argparse
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define valid transport types
VALID_TRANSPORT = {'container', 'liquid', 'solid'}

# Define default output folder
DEFAULT_OUTPUT_FOLDER = 'output'

def parse_name_reference(name_ref):
    """Parse name reference like {20201,401} into (page_id, t_id)"""
    if not name_ref:
        return None
    try:
        name_ref = name_ref.strip('{}')
        page_id, t_id = map(int, name_ref.split(','))
        return f"{page_id}_{t_id}"
    except:
        return None

def load_localization(file_path):
    """Load localization mappings from l044 file using page/t structure"""
    name_map = {}
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Find all page elements
        for page in root.findall('.//page'):
            page_id = page.get('id')
            if not page_id:
                continue

            # Process t elements within each page
            for t in page.findall('.//t'):
                t_id = t.get('id')
                if t_id:
                    # Create combined key: pageID_tID
                    key = f"{page_id}_{t_id}"
                    name_map[key] = t.text
        return name_map
    except Exception as e:
        logger.error(f"Error loading localization: {e}")
        return {}

def calculate_price_ranges(min_price, max_price):
    """Calculate price ranges as intervals around average using half range"""
    min_price = float(min_price)
    max_price = float(max_price)
    avg_price = (min_price + max_price) / 2
    half_range = (max_price - min_price) / 2

    def bound_price(price):
        if price < min_price:
            return min_price
        if price > max_price:
            return max_price
        return price

    ranges = {
        'avg': avg_price,
        '30_min': bound_price(avg_price - (0.30 * half_range)),
        '30_max': bound_price(avg_price + (0.30 * half_range)),
        '50_min': bound_price(avg_price - (0.50 * half_range)),
        '50_max': bound_price(avg_price + (0.50 * half_range)),
        '70_min': bound_price(avg_price - (0.70 * half_range)),
        '70_max': bound_price(avg_price + (0.70 * half_range))
    }
    return ranges

def get_base_folder():
    """Get base folder from args or user input"""
    parser = argparse.ArgumentParser(description='Process X4 ships data')
    parser.add_argument('folder', nargs='?', help='Base folder containing libraries and extensions subdirectories')
    parser.add_argument('--output-folder', default=DEFAULT_OUTPUT_FOLDER, help='Folder to store the output CSV files')
    args = parser.parse_args()

    if args.folder:
        base_folder = args.folder.strip()
        return base_folder, args.output_folder

    # If no argument provided, ask for input
    while True:
        folder = input("Please enter the path to X4 game folder: ").strip('" ').strip()
        if os.path.isdir(folder):
            return folder, DEFAULT_OUTPUT_FOLDER
        print("Invalid folder path. Please try again.")

def validate_folder_structure(base_folder):
    """Validate required folders and files exist"""
    libraries_path = os.path.join(base_folder, 'libraries')
    t_path = os.path.join(base_folder, 't')

    if not all(os.path.isdir(p) for p in [libraries_path, t_path]):
        raise FileNotFoundError(f"Required folders 'libraries' and 't' not found in {base_folder}")

    wares_path = os.path.join(libraries_path, 'wares.xml')
    loc_path = os.path.join(t_path, '0001-l044.xml')

    if not all(os.path.exists(p) for p in [wares_path, loc_path]):
        raise FileNotFoundError("Required XML files not found")

    return wares_path, loc_path

def find_wares_files(base_folder):
    """Find all wares.xml files with their sources"""
    wares_files = []

    # Add base game wares file
    base_wares = os.path.join(base_folder, 'libraries', 'wares.xml')
    if os.path.exists(base_wares):
        wares_files.append(('original', base_wares))

    # Search extensions
    extensions_path = os.path.join(base_folder, 'extensions')
    if os.path.exists(extensions_path):
        for ext_dir in os.listdir(extensions_path):
            ext_wares = os.path.join(extensions_path, ext_dir, 'libraries', 'wares.xml')
            if os.path.exists(ext_wares):
                wares_files.append((ext_dir, ext_wares))

    if not wares_files:
        raise FileNotFoundError("No wares.xml files found")

    logger.info(f"Found {len(wares_files)} wares.xml files")
    return wares_files

def process_all_wares(wares_files, name_map, output_folder):
    # Ensure the output folder exists
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            logger.info(f"Created output directory at: {output_folder}")
        except Exception as e:
            logger.error(f"Failed to create output directory '{output_folder}': {e}")
            return
    # Define output CSV file path
    output_path = os.path.join(output_folder, 'trade_wares_with_prices.csv')

    """Process all wares.xml files keeping source information"""
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['name', 'min', 'max', 'avg',
                        '30% min', '30% max',
                        '50% min', '50% max',
                        '70% min', '70% max',
                        'transport', 'source'])

        for source, wares_file in wares_files:
            tree = ET.parse(wares_file)
            root = tree.getroot()

            for ware in root.findall('.//ware'):
                if 'module' in ware.get('tags', '').split():
                    continue

                transport = ware.get('transport')
                if transport not in VALID_TRANSPORT:
                    continue

                name_ref = parse_name_reference(ware.get('name'))
                price = ware.find('price')

                if price is not None and name_ref:
                    name = name_map.get(name_ref, 'Unknown')
                    min_price = price.get('min')
                    max_price = price.get('max')

                    if min_price and max_price:
                        ranges = calculate_price_ranges(min_price, max_price)
                        writer.writerow([
                            name, min_price, max_price,
                            f"{ranges['avg']:.0f}",
                            f"{ranges['30_min']:.0f}",
                            f"{ranges['30_max']:.0f}",
                            f"{ranges['50_min']:.0f}",
                            f"{ranges['50_max']:.0f}",
                            f"{ranges['70_min']:.0f}",
                            f"{ranges['70_max']:.0f}",
                            transport,
                            source
                        ])

def main():
    try:
        base_folder, output_folder = get_base_folder()
        wares_files = find_wares_files(base_folder)
        loc_path = os.path.join(base_folder, 't', '0001-l044.xml')

        if not os.path.exists(loc_path):
            raise FileNotFoundError("Localization file not found")

        name_map = load_localization(loc_path)
        process_all_wares(wares_files, name_map, output_folder)
        logger.info("Processing complete")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

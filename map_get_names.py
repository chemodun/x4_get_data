import xml.etree.ElementTree as ET
import csv
import os
import logging
import argparse
import sys
import re

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define default exclusion patterns
DEFAULT_EXCLUDE_PATTERNS = [r'^timelines_map_', r'^demo_']

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
                    name_map[key] = t.text.strip() if t.text else ''

        logger.info(f"Loaded {len(name_map)} localization entries from {file_path}")
        return name_map
    except Exception as e:
        logger.error(f"Error loading localization: {e}")
        return {}

def find_mapdefaults_files(base_folder):
    """Find all mapdefaults.xml files with their sources"""
    mapdefaults_files = []

    # Add base game mapdefaults file
    base_mapdefaults = os.path.join(base_folder, 'libraries', 'mapdefaults.xml')
    if os.path.exists(base_mapdefaults):
        mapdefaults_files.append(('original', base_mapdefaults))

    # Search extensions
    extensions_path = os.path.join(base_folder, 'extensions')
    if os.path.exists(extensions_path):
        for ext_dir in os.listdir(extensions_path):
            ext_mapdefaults = os.path.join(extensions_path, ext_dir, 'libraries', 'mapdefaults.xml')
            if os.path.exists(ext_mapdefaults):
                mapdefaults_files.append((ext_dir, ext_mapdefaults))

    if not mapdefaults_files:
        logger.warning("No mapdefaults.xml files found")

    logger.info(f"Found {len(mapdefaults_files)} mapdefaults.xml files")
    return mapdefaults_files

def extract_cluster_sector(macro):
    """Extract cluster and sector IDs from macro string.

    Assumes the first numeric is cluster_id and the second is sector_id.
    If no sector_id is present, sector_id is set to 0 and type is 'cluster'.

    Returns:
        tuple: (cluster_id, sector_id, type)
    """
    numbers = re.findall(r'\d+', macro)
    if len(numbers) >= 2:
        cluster_id = int(numbers[0])
        sector_id = int(numbers[1])
        return (cluster_id, sector_id, 'sector')
    elif len(numbers) == 1:
        cluster_id = int(numbers[0])
        sector_id = 0
        return (cluster_id, sector_id, 'cluster')
    else:
        logger.warning(f"Could not extract cluster and sector IDs from macro: {macro}")
        return (0, 0, 'unknown')  # Default values if extraction fails

def resolve_placeholders(text, name_map, processed_keys=None, max_depth=10):
    """
    Recursively resolve placeholders in the format {pageID,tID} within the text.
    Removes any text within parentheses after resolution.

    Enhanced to accurately detect circular references by tracking processed keys per recursion path.
    """
    if processed_keys is None:
        processed_keys = []

    # Regex to find placeholders like {20201,401}
    pattern = re.compile(r'\{(\d+),(\d+)\}')

    def replacer(match):
        page_id, t_id = match.groups()
        key = f"{page_id}_{t_id}"

        # Prevent infinite recursion by checking if key is already in the current path
        if key in processed_keys:
            logger.warning(f"Circular reference detected for key: {key}")
            return match.group(0)  # Return as is

        processed_keys.append(key)  # Add key to the current path

        replacement = name_map.get(key, 'Unknown')
        if replacement == 'Unknown':
            logger.warning(f"Missing localization for key: {key}")
            processed_keys.pop()  # Remove key from the current path before returning
            return 'Unknown'

        # Recursively resolve if replacement contains more placeholders
        replacement = resolve_placeholders(replacement, name_map, processed_keys, max_depth - 1)

        processed_keys.pop()  # Remove key from the current path after resolving
        return replacement

    # Iterate up to max_depth to resolve nested placeholders
    current_text = text
    for depth in range(max_depth):
        new_text = pattern.sub(replacer, current_text)
        if new_text == current_text:
            break
        logger.debug(f"Depth {depth + 1}: {current_text} -> {new_text}")
        current_text = new_text
    else:
        logger.warning(f"Max recursion depth reached while resolving: {text}")

    # Remove any text within parentheses
    resolved_text = re.sub(r'\s*\([^)]*\)', '', current_text).strip()

    return resolved_text

def process_mapdefaults(mapdefaults_files, name_map, exclude_patterns, output_folder):
    """Process all mapdefaults.xml files and write to mapdefaults_output.csv sorted by cluster and sector."""
    all_rows = []

# Ensure the output folder exists
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            logger.info(f"Created output directory at: {output_folder}")
        except Exception as e:
            logger.error(f"Failed to create output directory '{output_folder}': {e}")
            return

    for source, mapdefaults_file in mapdefaults_files:
        try:
            tree = ET.parse(mapdefaults_file)
            root = tree.getroot()

            for dataset in root.findall('.//dataset'):
                macro = dataset.get('macro')
                if not macro:
                    continue

                macro = macro.strip()  # Remove leading and trailing spaces

                # Exclude macros matching any of the exclude patterns
                if any(re.match(pattern, macro) for pattern in exclude_patterns):
                    logger.info(f"Excluded macro '{macro}' from '{mapdefaults_file}' based on exclusion patterns.")
                    continue

                cluster_id, sector_id, entry_type = extract_cluster_sector(macro)

                identification = dataset.find('.//identification')
                if identification is not None:
                    name_attr = identification.get('name')
                    if not name_attr:
                        continue

                    name_attr = name_attr.strip()  # Remove leading and trailing spaces
                    name_ref = parse_name_reference(name_attr)
                    if not name_ref:
                        logger.warning(f"Invalid name reference '{name_attr}' in {mapdefaults_file}")
                        name = 'Unknown'
                    else:
                        raw_name = name_map.get(name_ref, 'Unknown')
                        name = resolve_placeholders(raw_name, name_map)

                    # Store tuple with sorting key and row data
                    row_data = (cluster_id, sector_id, entry_type, macro, name, source)
                    all_rows.append(row_data)
        except ET.ParseError as e:
            logger.error(f"XML parsing error in {mapdefaults_file}: {e}")
        except Exception as e:
            logger.error(f"Error processing {mapdefaults_file}: {e}")

    # Sort all_rows based on cluster_id and sector_id numerically
    all_rows.sort(key=lambda x: (x[0], x[1]))  # (cluster_id, sector_id)

    # Define output CSV file path
    output_path = os.path.join(output_folder, 'mapdefaults_output.csv')

    # Write to CSV including 'type'
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Headers including 'type'
        writer.writerow(['macro', 'name', 'source', 'type'])

        for row in all_rows:
            macro, name, source, entry_type = row[3], row[4], row[5], row[2]
            writer.writerow([macro, name, source, entry_type])

def get_base_folder():
    """Get base folder from args or user input"""
    parser = argparse.ArgumentParser(description='Process X4 localization data')
    parser.add_argument('folder', nargs='?', help='Base folder containing localization files')
    parser.add_argument('--output-folder', default=DEFAULT_OUTPUT_FOLDER, help='Folder to store the output CSV files')
    parser.add_argument('--exclude-macro-regex', nargs='*', default=DEFAULT_EXCLUDE_PATTERNS,
                        help='Regular expression patterns to exclude entries based on ID')
    args = parser.parse_args()

    base_folder = args.folder.strip() if args.folder else None
    output_folder = args.output_folder.strip()

    exclude_patterns = args.exclude_macro_regex

    if base_folder:
        return base_folder, exclude_patterns, output_folder

    # If no argument provided, ask for input
    while True:
        folder = input("Please enter the path to X4 game folder: ").strip('" ').strip()
        if os.path.isdir(folder):
            return folder, DEFAULT_EXCLUDE_PATTERNS, output_folder
        print("Invalid folder path. Please try again.")

def validate_folder_structure(base_folder):
    """Validate required folders and files exist"""
    libraries_path = os.path.join(base_folder, 'libraries')
    t_path = os.path.join(base_folder, 't')

    if not all(os.path.isdir(p) for p in [libraries_path, t_path]):
        raise FileNotFoundError(f"Required folders 'libraries' and 't' not found in {base_folder}")

    return libraries_path, t_path

def main():
    try:
        base_folder, exclude_patterns, output_folder = get_base_folder()
        libraries_path, t_path = validate_folder_structure(base_folder)

        # Find all mapdefaults.xml files
        mapdefaults_files = find_mapdefaults_files(base_folder)

        # Path to localization file
        loc_path = os.path.join(t_path, '0001-l044.xml')
        if not os.path.exists(loc_path):
            raise FileNotFoundError("Localization file '0001-l044.xml' not found")

        name_map = load_localization(loc_path)

        # Process mapdefaults.xml files with exclusion patterns
        if mapdefaults_files:
            process_mapdefaults(mapdefaults_files, name_map, exclude_patterns, output_folder)

        logger.info("Processing complete")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
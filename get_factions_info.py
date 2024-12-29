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

# Define default exclusion patterns if any (adjust as needed)
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
                    name_map[key] = t.text if t.text else ''

        logger.info(f"Loaded {len(name_map)} localization entries from {file_path}")
        return name_map
    except Exception as e:
        logger.error(f"Error loading localization: {e}")
        return {}

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

def find_factions_files(base_folder):
    """Find all factions.xml files with their sources"""
    factions_files = []

    # Add base game factions.xml file
    base_factions = os.path.join(base_folder, 'libraries', 'factions.xml')
    if os.path.exists(base_factions):
        factions_files.append(('original', base_factions))
        logger.info(f"Found factions.xml in original libraries: {base_factions}")

    # Search extensions for factions.xml
    extensions_path = os.path.join(base_folder, 'extensions')
    if os.path.exists(extensions_path):
        for ext_dir in os.listdir(extensions_path):
            ext_factions = os.path.join(extensions_path, ext_dir, 'libraries', 'factions.xml')
            if os.path.exists(ext_factions):
                factions_files.append((ext_dir, ext_factions))
                logger.info(f"Found factions.xml in extension '{ext_dir}': {ext_factions}")

    if not factions_files:
        logger.warning("No factions.xml files found")
    else:
        logger.info(f"Total factions.xml files found: {len(factions_files)}")

    return factions_files

def process_factions(factions_files, name_map, exclude_patterns, output_folder):
    """Process all factions.xml files and write to factions_output.csv with resolved names."""
    all_rows = []

  # Ensure the output folder exists
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            logger.info(f"Created output directory at: {output_folder}")
        except Exception as e:
            logger.error(f"Failed to create output directory '{output_folder}': {e}")
            return

    for source, factions_file in factions_files:
        try:
            tree = ET.parse(factions_file)
            root = tree.getroot()

            for faction in root.findall('.//faction'):
                faction_id = faction.get('id', '').strip()
                if not faction_id:
                    logger.warning(f"Faction without ID found in {factions_file}. Skipping entry.")
                    continue  # Skip factions without valid ID

                # Extract attributes
                name_ref = faction.get('name', '').strip()
                shortname_ref = faction.get('shortname', '').strip()
                prefixname_ref = faction.get('prefixname', '').strip()
                spacename_ref = faction.get('spacename', '').strip()
                homespacename_ref = faction.get('homespacename', '').strip()
                primaryrace = faction.get('primaryrace', '').strip()

                # Resolve placeholders
                name = resolve_placeholders(name_ref, name_map)
                shortname = resolve_placeholders(shortname_ref, name_map)
                prefixname = resolve_placeholders(prefixname_ref, name_map)
                spacename = resolve_placeholders(spacename_ref, name_map)
                homespacename = resolve_placeholders(homespacename_ref, name_map)

                # Apply exclusion patterns if necessary (currently not used, can be adjusted)
                macro = f"id_{faction_id}"
                if any(re.match(pattern, macro) for pattern in exclude_patterns):
                    logger.info(f"Excluded faction '{faction_id}' from '{factions_file}' based on exclusion patterns.")
                    continue

                # Append the row
                all_rows.append({
                    'id': faction_id,
                    'name': name,
                    'shortname': shortname,
                    'prefixname': prefixname,
                    'spacename': spacename,
                    'homespacename': homespacename,
                    'primaryrace': primaryrace,
                    'source': source
                })

        except ET.ParseError as e:
            logger.error(f"XML parsing error in {factions_file}: {e}")
        except Exception as e:
            logger.error(f"Error processing {factions_file}: {e}")

    if not all_rows:
        logger.warning("No faction data extracted from factions.xml files")
        return

    # Define CSV columns
    csv_columns = ['id', 'name', 'shortname', 'prefixname', 'spacename', 'homespacename', 'primaryrace', 'source']

    output_path = os.path.join(output_folder, 'factions_output.csv')

    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()

            for row in all_rows:
                writer.writerow(row)

        logger.info("factions_output.csv has been created successfully")
    except IOError as e:
        logger.error(f"IO error while writing CSV: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while writing CSV: {e}")

def get_base_folder():
    """Get base folder from args or user input"""
    parser = argparse.ArgumentParser(description='Process X4 factions data')
    parser.add_argument('folder', nargs='?', help='Base folder containing libraries and extensions subdirectories')
    parser.add_argument('--exclude-macro-regex', nargs='*', default=DEFAULT_EXCLUDE_PATTERNS,
                        help='Regular expression patterns to exclude factions based on ID')
    parser.add_argument('--output-folder', default=DEFAULT_OUTPUT_FOLDER, help='Folder to store the output CSV files')
    args = parser.parse_args()

    if args.folder:
        base_folder = args.folder.strip()
        exclude_patterns = [pattern.strip() for pattern in args.exclude_macro_regex]
        return base_folder, exclude_patterns, args.output_folder

    # If no argument provided, ask for input
    while True:
        folder = input("Please enter the path to X4 game folder: ").strip('" ').strip()
        if os.path.isdir(folder):
            return folder, DEFAULT_EXCLUDE_PATTERNS, DEFAULT_OUTPUT_FOLDER
        print("Invalid folder path. Please try again.")

def validate_folder_structure(base_folder):
    """Validate required folders and files exist"""
    libraries_path = os.path.join(base_folder, 'libraries')
    extensions_path = os.path.join(base_folder, 'extensions')

    if not os.path.isdir(libraries_path):
        raise FileNotFoundError(f"'libraries' folder not found in {base_folder}")

    if not os.path.isdir(extensions_path):
        logger.warning(f"'extensions' folder not found in {base_folder}. Proceeding without extensions.")

    return libraries_path, extensions_path

def main():
    try:
        base_folder, exclude_patterns, output_folder = get_base_folder()
        libraries_path, extensions_path = validate_folder_structure(base_folder)

        # Path to localization file
        loc_path = os.path.join(base_folder, 't', '0001-l044.xml')
        if not os.path.exists(loc_path):
            raise FileNotFoundError("Localization file '0001-l044.xml' not found in 't' directory")

        name_map = load_localization(loc_path)

        # Find all factions.xml files
        factions_files = find_factions_files(base_folder)

        # Process factions.xml files with exclusion patterns
        if factions_files:
            process_factions(factions_files, name_map, exclude_patterns, output_folder)
        else:
            logger.warning("No factions.xml files to process")

        logger.info("Processing complete")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
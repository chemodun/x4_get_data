import xml.etree.ElementTree as ET
import csv
import os
import logging
import argparse
import sys
import re

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define default output folder
DEFAULT_OUTPUT_FOLDER = 'output'

def find_ships_files(base_folder):
    """
    Find all ships.xml files within the base_folder and its subdirectories.
    Determine the source of each ships.xml file based on its location.

    Returns:
        List of tuples: (source, ships_file_path)
    """
    ships_files = []

    # Add base game ships.xml file
    base_ships = os.path.join(base_folder, 'libraries', 'ships.xml')
    if os.path.exists(base_ships):
        ships_files.append(('original', base_ships))
        logger.info(f"Found ships.xml in original libraries: {base_ships}")

    # Search extensions for ships.xml
    extensions_path = os.path.join(base_folder, 'extensions')
    if os.path.exists(extensions_path):
        for ext_dir in os.listdir(extensions_path):
            ext_map_dir = os.path.join(extensions_path, ext_dir, 'libraries')
            ext_ships = os.path.join(ext_map_dir, 'ships.xml')
            if os.path.exists(ext_ships):
                ships_files.append((ext_dir, ext_ships))
                logger.info(f"Found ships.xml in extension '{ext_dir}': {ext_ships}")

    if not ships_files:
        logger.warning("No ships.xml files found")
    else:
        logger.info(f"Total ships.xml files found: {len(ships_files)}")

    return ships_files

def process_ships(ships_files, output_folder):
    """
    Process all ships.xml files and write to ships_output.csv with id, group, size, source,
    and dynamic columns for factions and tags.

    Args:
        ships_files (list): List of tuples containing (source, ships_file_path)
    """
    ships_data = []
    factions_set = set()
    tags_set = set()

    for source, ships_file in ships_files:
        try:
            tree = ET.parse(ships_file)
            root = tree.getroot()

            for ship in root.findall('ship'):
                ship_id = ship.get('id', '').strip()
                if not ship_id:
                    logger.warning(f"Ship without ID found in {ships_file}. Skipping entry.")
                    # Log the structure of the ship
                    ship_str = ET.tostring(ship, encoding='unicode')
                    logger.debug(f"Ship details: {ship_str}")
                    continue  # Skip ships without valid ID

                group = ship.get('group', '').strip()

                # Extract size from category
                category = ship.find('category')
                size = category.get('size', '').strip() if category is not None else ''

                # Extract faction and tags
                faction = category.get('faction', '').strip() if category is not None else ''
                tags = category.get('tags', '').strip() if category is not None else ''

                # Process factions
                factions = re.findall(r'\w+', faction)
                for f in factions:
                    factions_set.add(f)

                # Process tags
                tags = re.findall(r'\w+', tags)
                for tag in tags:
                    tags_set.add(tag)

                ships_data.append({
                    'id': ship_id,
                    'group': group,
                    'size': size,
                    'source': source,
                    'factions': factions,
                    'tags': tags
                })
        except ET.ParseError as e:
            logger.error(f"XML parsing error in {ships_file}: {e}")
        except Exception as e:
            logger.error(f"Error processing {ships_file}: {e}")

    if not ships_data:
        logger.warning("No ship data extracted from ships.xml files")
        return

    # Enclose faction names in () and tag names in []
    enclosed_factions = {f: f"({f})" for f in factions_set}
    enclosed_tags = {t: f"[{t}]" for t in tags_set}

    # Create sorted lists of unique enclosed factions and tags
    sorted_factions = sorted(enclosed_factions.values())
    sorted_tags = sorted(enclosed_tags.values())

    # Define CSV columns with enclosed names
    csv_columns = ['id', 'group', 'size', 'source'] + sorted_factions + sorted_tags

    # Define output file path
    output_path = os.path.join(output_folder, 'ships_output.csv')

    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()

            for ship in ships_data:
                row = {
                    'id': ship['id'],
                    'group': ship['group'],
                    'size': ship['size'],
                    'source': ship['source']
                }

                # Initialize all enclosed faction columns to 'FALSE'
                for enclosed_faction in sorted_factions:
                    row[enclosed_faction] = 'FALSE'

                # Initialize all enclosed tag columns to 'FALSE'
                for enclosed_tag in sorted_tags:
                    row[enclosed_tag] = 'FALSE'

                # Set 'TRUE' for factions present in the ship
                for faction in ship['factions']:
                    enclosed_faction = enclosed_factions.get(faction)
                    if enclosed_faction:
                        row[enclosed_faction] = 'TRUE'

                # Set 'TRUE' for tags present in the ship
                for tag in ship['tags']:
                    enclosed_tag = enclosed_tags.get(tag)
                    if enclosed_tag:
                        row[enclosed_tag] = 'TRUE'

                writer.writerow(row)

        logger.info("ships_output.csv has been created successfully")
    except IOError as e:
        logger.error(f"IO error while writing CSV: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while writing CSV: {e}")

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
    """
    Validate that the required 'libraries' and 'extensions' directories exist.

    Args:
        base_folder (str): Path to the base game folder

    Raises:
        FileNotFoundError: If required directories are missing
    """
    libraries_path = os.path.join(base_folder, 'libraries')
    extensions_path = os.path.join(base_folder, 'extensions')

    if not os.path.isdir(libraries_path):
        raise FileNotFoundError(f"'libraries' folder not found in {base_folder}")

    if not os.path.isdir(extensions_path):
        logger.warning(f"'extensions' folder not found in {base_folder}. Proceeding without extensions.")

    return libraries_path, extensions_path

def main():
    try:
        base_folder, output_folder = get_base_folder()
        validate_folder_structure(base_folder)

        # Find all ships.xml files
        ships_files = find_ships_files(base_folder)

        # Process ships.xml files
        if ships_files:
            process_ships(ships_files, output_folder)
        else:
            logger.warning("No ships.xml files to process")

        logger.info("Processing complete")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
import os
import re
from pathlib import Path


def extract_number(filename):
    """
    Extract chapter number from filename like Chapter_12.txt
    """
    match = re.search(r'Chapter_(\d+)\.txt', filename, re.IGNORECASE)
    return int(match.group(1)) if match else -1


def merge_chapters(input_folder, output_folder, batch_size=20):
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    # Create output folder if not exists
    output_path.mkdir(parents=True, exist_ok=True)

    # Get all Chapter_*.txt files
    files = [
        f for f in input_path.iterdir()
        if f.is_file() and re.match(r'Chapter_\d+\.txt', f.name, re.IGNORECASE)
    ]

    # Sort by chapter number
    files.sort(key=lambda f: extract_number(f.name))

    if not files:
        print("No Chapter_*.txt files found.")
        return

    # Merge in batches of 20
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]

        start_num = extract_number(batch[0].name)
        end_num = extract_number(batch[-1].name)

        output_file = output_path / f"Chapter_{start_num}-{end_num}.txt"

        with open(output_file, "w", encoding="utf-8") as outfile:
            for file in batch:
                with open(file, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())
                    outfile.write("\n\n")  # spacing between chapters

        print(f"Created: {output_file.name}")


if __name__ == "__main__":
    input_folder = r".\translated_chapters"
    output_folder = r".\batched_chapter"

    merge_chapters(input_folder, output_folder, batch_size=20)
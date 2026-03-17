import zipfile
import os
import pickle
from pathlib import Path
from bs4 import BeautifulSoup
import re


def extract_chapters_from_epub(epub_path, start_chapter_num):
    """
    Extract individual chapters from an EPUB file, skipping the first content file (outline).
    
    Args:
        epub_path: Path to the EPUB file
        start_chapter_num: The global starting chapter number
        
    Returns:
        Tuple: (List of dictionaries containing chapter data, next available chapter number)
    """
    chapters = []
    chapter_num = start_chapter_num
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as zip_ref:
            # Get list of all files in the EPUB
            file_list = zip_ref.namelist()
            
            # Filter for HTML/XHTML content files
            content_files = [f for f in file_list 
                           if f.endswith(('.html', '.xhtml', '.htm'))]
            
            # Sort to maintain reading order
            content_files.sort()
            
            skipped_outline = False
            
            for content_file in content_files:
                try:
                    # Read the HTML content
                    with zip_ref.open(content_file) as f:
                        html_content = f.read()
                        
                    # Parse HTML and extract text
                    soup = BeautifulSoup(html_content, 'xml')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Get text and clean up whitespace
                    text = soup.get_text(separator=' ')
                    text = re.sub(r'\s+', ' ', text).strip()
                    
                    # Only process if there's substantial content (more than 100 chars)
                    if text and len(text) > 100:
                        
                        # Skip the first valid text file (Outline) for every EPUB file
                        if not skipped_outline:
                            skipped_outline = True
                            continue
                            
                        # Try to extract chapter title from the text or filename
                        title = extract_chapter_title(soup, content_file)
                        
                        chapter_data = {
                            'chapter_id': chapter_num,
                            'title': title,
                            'filename': content_file,
                            'text': text,
                            'length': len(text)
                        }
                        chapters.append(chapter_data)
                        chapter_num += 1
                        
                except Exception as e:
                    print(f"Warning: Could not process {content_file} in {epub_path}: {e}")
                    continue
    
    except Exception as e:
        print(f"Error: Could not open {epub_path}: {e}")
        return [], chapter_num
    
    return chapters, chapter_num


def extract_chapter_title(soup, filename):
    """
    Try to extract chapter title from HTML content.
    """
    for tag in ['h1', 'h2', 'h3', 'title']:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text().strip()
            if title and len(title) < 200:
                return title
    
    return os.path.basename(filename)


# ========== CHAPTER ACCESS FUNCTIONS ==========

def load_chapters(pickle_file="./text.pkl"):
    """
    Load all chapters from the pickle file.
    """
    with open(pickle_file, 'rb') as f:
        return pickle.load(f)


def get_chapter_by_id(chapter_id, pickle_file="./text.pkl"):
    """
    Get a specific chapter by its sequential ID.
    
    Args:
        chapter_id: The integer chapter ID
        pickle_file: Path to the pickle file
        
    Returns:
        Dictionary containing chapter data, or None if not found
    """
    chapters = load_chapters(pickle_file)
    for chapter in chapters:
        if chapter['chapter_id'] == chapter_id:
            return chapter
    return None


def get_chapter_text(chapter_id, pickle_file="./text.pkl"):
    """
    Get just the text content of a specific chapter.
    """
    chapter = get_chapter_by_id(chapter_id, pickle_file)
    return chapter['text'] if chapter else None


def list_chapters(pickle_file="./text.pkl"):
    """
    List all available chapters with basic info.
    """
    chapters = load_chapters(pickle_file)
    print(f"Total chapters extracted: {len(chapters)}\n")
    print(f"{'='*60}")
    
    for chapter in chapters:
        print(f"  Chapter {chapter['chapter_id']}: {chapter['title']}")
        print(f"    Length: {chapter['length']:,} characters")


def search_chapters(query, pickle_file="./text.pkl"):
    """
    Search for chapters containing specific text.
    """
    chapters = load_chapters(pickle_file)
    query_lower = query.lower()
    return [ch for ch in chapters if query_lower in ch['text'].lower()]


# ========== MAIN PROCESSING FUNCTION ==========

def main():
    """
    Main function to process all EPUB files and create combined binary file.
    """
    # Configuration
    epub_folder = "./epub/"
    output_file = "./text.pkl"
    
    # Collect all EPUB files (1.epub to 9.epub)
    epub_files = []
    for i in range(1, 10):
        epub_path = os.path.join(epub_folder, f"{i}.epub")
        if os.path.exists(epub_path):
            epub_files.append(epub_path)
        else:
            print(f"Warning: {epub_path} not found, skipping...")
    
    if not epub_files:
        print("Error: No EPUB files found!")
        return
    
    print(f"Found {len(epub_files)} EPUB files")
    print("=" * 60)
    
    all_chapters = []
    global_chapter_num = 1
    
    for epub_path in epub_files:
        print(f"\nProcessing {os.path.basename(epub_path)}...")
        
        chapters, global_chapter_num = extract_chapters_from_epub(epub_path, global_chapter_num)
        
        if chapters:
            all_chapters.extend(chapters)
            print(f"  Extracted {len(chapters)} chapters (Ignored outline)")
            total_chars = sum(ch['length'] for ch in chapters)
            print(f"  Characters in these chapters: {total_chars:,}")
        else:
            print(f"  Warning: No chapters extracted from {epub_path}")
    
    print("\n" + "=" * 60)
    print(f"Total chapters extracted globally: {len(all_chapters)}")
    total_chars = sum(ch['length'] for ch in all_chapters)
    print(f"Total characters globally: {total_chars:,}")
    
    # Save to binary file using pickle
    print(f"\nSaving to {output_file}...")
    with open(output_file, 'wb') as f:
        pickle.dump(all_chapters, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    print("Done! Binary file created successfully.")
    print("\nData structure saved:")
    print("  - List of dictionaries")
    print("  - Each dict contains:")
    print("      chapter_id: Sequential chapter number (1, 2, 3...)")
    print("      title: Chapter title")
    print("      filename: Source HTML file")
    print("      text: Chapter text content")
    print("      length: Character count")
    
    print("\nUsage examples:")
    print("  from extract_text_from_epub import *")
    print("  ")
    print("  # Get chapter by its sequential ID")
    print("  chapter = get_chapter_by_id(3)  # Chapter 3 overall")
    print("  ")
    print("  # Get just the text")
    print("  text = get_chapter_text(3)")
    print("  ")
    print("  # List all chapters")
    print("  list_chapters()")
    print("  ")
    print("  # Search chapters")
    print("  results = search_chapters('dragon')")
    
    # Also create a plain text version for reference
    text_output = "./text.txt"
    print(f"\nAlso creating plain text version: {text_output}")
    with open(text_output, 'w', encoding='utf-8') as f:
        for chapter in all_chapters:
            f.write(f"\n{'-'*80}\n")
            f.write(f"Chapter {chapter['chapter_id']}: {chapter['title']}\n")
            f.write(f"{'-'*80}\n\n")
            f.write(chapter['text'])
            f.write("\n\n")
    
    print("Plain text version created for reference.")


if __name__ == "__main__":
    main()
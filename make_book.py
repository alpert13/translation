import os
import re
from ebooklib import epub

def detect_volume_and_chapter(content):
    """
    Detect if this is a volume start and extract volume/chapter titles
    Returns: (is_volume_start, volume_title, chapter_title)
    """
    lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
    if not lines:
        return False, None, None
    
    first_line = lines[0].replace('*', '').replace('#', '').strip()
    
    # Check if it's a volume start (contains "Quyển" or "Volume")
    if len(lines) >= 2 and ('Quyển' in first_line or 'Volume' in first_line):
        volume_title = first_line
        chapter_title = lines[1].replace('*', '').replace('#', '').strip()
        return True, volume_title, chapter_title
    else:
        return False, None, first_line

def create_epub_from_txt(txt_files, output_file="LOTM.epub", book_title="Quỷ bí chi chủ", author="Mực thích lặn nước"):
    """
    Creates a beautifully formatted EPUB from text files with proper styling
    """
    # 1. Create an EPUB book object and set metadata
    book = epub.EpubBook()
    book.set_identifier("id_lotm_vi_001")
    book.set_title(book_title)
    book.set_language("vi")
    book.add_author(author)
    
    # 2. Add custom CSS for beautiful formatting
    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    
    body {
        font-family: "Palatino Linotype", "Book Antiqua", Palatino, serif;
        font-size: 1.1em;
        line-height: 1.8;
        margin: 2em;
        text-align: justify;
        color: #2c3e50;
    }
    
    h1 {
        font-size: 2.2em;
        font-weight: bold;
        text-align: center;
        margin-top: 2em;
        margin-bottom: 0.5em;
        color: #8b0000;
        border-bottom: 3px solid #8b0000;
        padding-bottom: 0.3em;
        letter-spacing: 0.05em;
    }
    
    h2 {
        font-size: 1.8em;
        font-weight: bold;
        text-align: center;
        margin-top: 1.5em;
        margin-bottom: 1em;
        color: #2c3e50;
        letter-spacing: 0.03em;
    }
    
    .volume-title {
        font-size: 2em;
        font-weight: bold;
        text-align: center;
        margin-top: 3em;
        margin-bottom: 0.3em;
        color: #8b0000;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        border-top: 3px solid #8b0000;
        border-bottom: 3px solid #8b0000;
        padding: 0.5em 0;
    }
    
    .chapter-title {
        font-size: 1.8em;
        font-weight: bold;
        text-align: center;
        margin-top: 1em;
        margin-bottom: 2em;
        color: #34495e;
        letter-spacing: 0.05em;
    }
    
    p {
        margin-top: 0;
        margin-bottom: 1em;
        text-indent: 2em;
        line-height: 1.8;
    }
    
    p:first-of-type {
        text-indent: 0;
        margin-top: 1.5em;
    }
    
    /* Drop cap for first paragraph */
    .first-paragraph::first-letter {
        font-size: 3.5em;
        font-weight: bold;
        float: left;
        line-height: 0.9;
        margin: 0.05em 0.1em 0 0;
        color: #8b0000;
    }
    
    em {
        font-style: italic;
    }
    
    strong {
        font-weight: bold;
        color: #2c3e50;
    }
    
    hr {
        border: none;
        border-top: 1px solid #bdc3c7;
        margin: 2em 0;
    }
    
    /* Scene break ornament */
    .scene-break {
        text-align: center;
        margin: 2em 0;
        font-size: 1.5em;
        color: #8b0000;
    }
    
    /* Chapter ornament */
    .chapter-ornament {
        text-align: center;
        margin: 1em 0 2em 0;
        font-size: 1.2em;
        color: #8b0000;
    }
    '''
    
    css = epub.EpubItem(
        uid="style",
        file_name="style/style.css",
        media_type="text/css",
        content=style
    )
    book.add_item(css)
    
    chapters = []
    current_volume = None
    
    # 3. Process each text file
    for i, txt_file in enumerate(txt_files):
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Detect volume and chapter information
        is_volume_start, volume_title, chapter_title = detect_volume_and_chapter(content)
        
        if is_volume_start:
            current_volume = volume_title
        
        # Prepare the chapter title for TOC
        if not chapter_title:
            chapter_title = f"Chương {i+1}"
        
        # Process content: split into paragraphs
        lines = content.strip().split('\n')
        processed_lines = []
        skip_count = 0
        
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Skip the first 1-2 lines that are titles
            if is_volume_start and skip_count < 2:
                skip_count += 1
                continue
            elif not is_volume_start and skip_count < 1:
                skip_count += 1
                continue
            
            # Convert markdown bold/italic
            line = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', line)
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            
            processed_lines.append(line)
        
        # Build HTML content
        html_body = []
        
        # Add volume title if this is a volume start
        if is_volume_start and current_volume:
            html_body.append(f'<div class="volume-title">{current_volume}</div>')
            html_body.append('<div class="chapter-ornament">❦</div>')
        
        # Add chapter title
        html_body.append(f'<h2 class="chapter-title">{chapter_title}</h2>')
        
        # Add content paragraphs
        for idx, line in enumerate(processed_lines):
            if idx == 0:
                # First paragraph with drop cap
                html_body.append(f'<p class="first-paragraph">{line}</p>')
            else:
                html_body.append(f'<p>{line}</p>')
        
        html_content = '\n'.join(html_body)
        
        # 4. Create chapter object
        file_name = f"chap_{i+1:04d}.xhtml"
        c = epub.EpubHtml(title=chapter_title, file_name=file_name, lang='vi')
        
        # Set content with proper HTML structure
        c.set_content(f'''<html xmlns="http://www.w3.org/1999/xhtml" lang="vi">
<head>
    <title>{chapter_title}</title>
    <link rel="stylesheet" type="text/css" href="style/style.css"/>
</head>
<body>
    {html_content}
</body>
</html>'''.encode('utf-8'))
        
        book.add_item(c)
        chapters.append(c)
    
    # 5. Create Table of Contents
    book.toc = tuple(chapters)
    
    # 6. Add required navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # 7. Define spine (reading order)
    book.spine = ['nav'] + chapters
    
    # 8. Write EPUB file
    epub.write_epub(output_file, book)
    print(f"✓ Đã tạo thành công: {output_file}")
    print(f"✓ Tổng số chương: {len(chapters)}")

def extract_number(filename):
    """Extract chapter number from filename"""
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else 0

if __name__ == "__main__":
    folder_path = "translated_chapters"
    
    # Get all .txt files
    txt_files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.endswith(".txt")
    ]
    
    # Sort by chapter number
    txt_files.sort(key=lambda x: extract_number(os.path.basename(x)))
    
    # Process first 10 chapters (remove this line to process all)
    
    if txt_files:
        create_epub_from_txt(
            txt_files=txt_files,
            output_file="Quy_Bi_Chi_Chu_Beautiful.epub",
            book_title="Quỷ Bí Chi Chủ",
            author="Mực Thích Lặn Nước"
        )
    else:
        print("⚠ Không tìm thấy file .txt nào trong folder.")
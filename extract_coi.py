import os
import pickle
from data import extract_chapters_from_epub

def main():
    epub_path = "./epub/Circle of Inevitability .epub"
    output_file = "./coi_text.pkl"
    text_output = "./coi_text.txt"
    
    print(f"Processing {epub_path}...")
    
    chapters, global_chapter_num = extract_chapters_from_epub(epub_path, 1)
    
    if chapters:
        print(f"Extracted {len(chapters)} chapters")
        total_chars = sum(ch['length'] for ch in chapters)
        print(f"Total characters: {total_chars:,}")
        
        print(f"Saving to {output_file}...")
        with open(output_file, 'wb') as f:
            pickle.dump(chapters, f, protocol=pickle.HIGHEST_PROTOCOL)
            
        print(f"Saving plain text to {text_output}...")
        with open(text_output, 'w', encoding='utf-8') as f:
            for chapter in chapters:
                f.write(f"\n{'-'*80}\n")
                f.write(f"Chapter {chapter['chapter_id']}: {chapter['title']}\n")
                f.write(f"{'-'*80}\n\n")
                f.write(chapter['text'])
                f.write("\n\n")
        print("Done!")
    else:
        print("No chapters extracted!")

if __name__ == "__main__":
    main()

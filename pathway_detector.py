import json
import re
import regex

def fuzzy_substring_search(pattern, text, max_dist=1):
    pattern = pattern.lower()
    text = text.lower()
    
    # 1. Fast exact word match check
    if re.search(r'\b' + re.escape(pattern) + r'\b', text):
        return True
        
    if max_dist == 0:
        return False

    # 2. Use optimized regex fuzzy matching
    fuzzy_pattern = f"(?e)({regex.escape(pattern)}){{e<={max_dist}}}"
    match = regex.search(fuzzy_pattern, text)
    return bool(match)

def detect_pathways(text, pathway_json_path="pathway.json"):
    try:
        with open(pathway_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {pathway_json_path}: {e}")
        return {"pathway": []}
        
    detected_pathways = []
    
    for pw in data.get("pathway", []):
        pw_name = pw.get("pathway_name", "")
        detected_list = []
        
        for seq in pw.get("list", []):
            eng_name = seq.get("eng_name", "")
            if not eng_name:
                continue
                
            # determine max dist based on length
            if len(eng_name) <= 4:
                max_dist = 0
            elif len(eng_name) <= 8:
                max_dist = 1
            else:
                max_dist = 2
                
            if fuzzy_substring_search(eng_name, text, max_dist=max_dist):
                detected_list.append({
                    "eng_name": eng_name,
                    "vi_name": seq.get("vi_name", ""),
                    "index": seq.get("index", 0)
                })
                
        if detected_list:
            detected_list.sort(key=lambda x: x["index"], reverse=True)
            detected_pathways.append({
                "pathway_name": pw_name,
                "list": detected_list
            })
            
    return {"pathway": detected_pathways}

def get_pathway_json_block(text, pathway_json_path="pathway.json"):
    result = detect_pathways(text, pathway_json_path)
    pathways = result.get("pathway", [])
    if not pathways:
        return ""

    lines = []
    for pw in pathways:
        pw_name = pw.get("pathway_name", "")
        # Trích tên tiếng Việt của con đường từ "Error (Sai Lầm)" -> "Sai Lầm"
        m = re.search(r'\(([^)]+)\)', pw_name)
        pw_vi_name = m.group(1) if m else pw_name

        for item in pw.get("list", []):
            eng = item.get("eng_name", "")
            vi  = item.get("vi_name", "")
            idx = item.get("index", 0)
            lines.append(f"{eng}: {vi} (Con đường {pw_vi_name}, danh sách {idx})")

    return "\n".join(lines)

if __name__ == "__main__":
    test_text = "He is a Bizarro-Sorcerer and also a seer from the Sun pathway. In the end, he became a Bizzaro Sssorcerer."
    print("Test text:", test_text)
    print("Result:")
    print(get_pathway_json_block(test_text))

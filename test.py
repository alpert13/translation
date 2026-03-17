from data import list_chapters

with open("text.txt", "r", encoding="utf-8") as f:
    text = f.read()

words = text.split()
print(len(words))
list_chapters()

def build_prompt(title: str, text: str, relevant_glossary: dict, pathway_list: str = "") -> str:
    glossary_text = "\n".join([f"- {k}: {v}" for k, v in relevant_glossary.items()])
    if not glossary_text:
        glossary_text = "(Không có thuật ngữ nào liên quan được tìm thấy)"

    prompt = f"""Bạn là một dịch giả tiểu thuyết mạng (web novel) chuyên nghiệp. Hãy dịch chương truyện "Circle of Inevitability" sau sang tiếng Việt.

[BỐI CẢNH & VĂN PHONG]
- Bối cảnh: Thế giới giả tưởng mang phong cách Châu Âu thời kỳ Victoria, kết hợp yếu tố Steampunk và kinh dị kỳ bí (Cthulhu Mythos).
- Văn phong: Bí ẩn, miêu tả chi tiết, đôi khi rùng rợn. Sử dụng từ ngữ chau chuốt, kết hợp hài hòa giữa từ Thuần Việt và Hán Việt để tạo cảm giác kỳ ảo (fantasy) nhưng không được quá sến hay cổ hiệp. Lời thoại cần tự nhiên, mang hơi hướm quý tộc phương Tây khi cần.

[THUẬT NGỮ CHO CHƯƠNG NÀY]
{glossary_text}


[CÁC DANH SÁCH CON ĐƯỜNG XUẤT HIỆN TRONG CHƯƠNG NÀY]
{pathway_list}

[QUY TẮC DỊCH]
- Tên riêng & Địa danh: Giữ nguyên tên gốc, ưu tiên đọc theo âm Pháp/Anh nếu là từ gốc (Ví dụ: Lumian Lee, Aurore Lee, Cordu, Trier, Intis). KHÔNG phiên âm sang tiếng Việt.
- Tiền tệ: Giữ nguyên hệ thống tiền tệ (Ví dụ: Verl d'Or, Coppet, Lick).
- Xưng hô (Cực kỳ quan trọng):
  + Lumian (nhân vật chính) tự xưng trong suy nghĩ là "hắn" hoặc "mình". Gọi chị gái Aurore là "chị" - "em".
  + Các nhân vật (ở Trier/Intis) thường gọi giao tiếp lịch sự với các danh xưng tiếng Pháp như Monsieur (Ngài), Madame (Phu nhân), Mademoiselle (Tiểu thư).
  + Thành viên Hội Bài Tarot gọi nhau như Ngài/Tiểu thư + Tên lá bài (Ví dụ: Madam Magician -> Phu nhân Ma Thuật, Madam Justice -> Phu nhân Chính Nghĩa).
- Diễn đạt: Không dịch "word by word". Hãy cấu trúc lại câu cho đúng ngữ pháp và văn phong tiếng Việt nhưng không làm mất ý nghĩa gốc.
- Dịch cả [TIÊU ĐỀ CHƯƠNG] và [NỘI DUNG].

[QUY TẮC ĐỊNH DẠNG (FORMAT)]
- Giữ nguyên cấu trúc dòng và đoạn văn (paragraph) của bản gốc. Tuyệt đối không tự ý gộp hay chia nhỏ các đoạn văn.
- Lời thoại nhân vật đặt trong dấu ngoặc kép `""`, suy nghĩ trong đầu đặt trong dấu sao (*).
- Dùng dấu chấm lửng chuẩn `...` (3 dấu chấm).
- Tiêu đề chương phải được in đậm.
- Khoảng cách các đoạn: Giữa các đoạn văn cách nhau một dòng trống (Enter 2 lần) để dễ đọc.
- Không cần quan tâm các dấu của văn bản gốc, tự sử dụng các dấu theo quy tắt ở trên.


[YÊU CẦU ĐẶC BIỆT - HỌC TỪ VỰNG MỚI]
1. Nếu xuất hiện Tên riêng, Tổ chức, Vật phẩm MỚI chưa có trong Bảng thuật ngữ, hãy tự dịch cho hay và phù hợp với ngữ cảnh.
2. BẮT BUỘC liệt kê thuật ngữ mới ở CUỐI CÙNG bản dịch trong cặp ngoặc vuông, cách nhau bởi '|'. (Ví dụ: [The Fool: Kẻ Khờ | Blasphemy Slate: Phiến Đá Phỉ Báng]). Nếu không có từ mới, ghi: []
3. Không giải thích gì thêm, chỉ in ra bản dịch và danh sách từ vựng.
4. Các từ có nếu được giữ nguyên bản gốc thì không cần liệt kê vào danh sách từ vựng.
5. Những thuật ngữ không xuất hiện trong chương thì nghiêm cấm không được đưa vào danh sách từ vựng


ví dụ đầu ra, đảm bảo giống như thế này, không được có bất kỳ thêm bớt, thay đổi nào:
**Chương 1: Foreigner**

"Mọi quà tặng của số phận đều đi kèm một cái giá phải trả" - trích từ tác phẩm Mary Queen of Scots của Zweig.
"Tôi chỉ là kẻ vô danh...
...
...
...

[Eternal Blazing Sun Church: Giáo Hội Mặt Trời Rực Lửa Vĩnh Hằng | The Fool: Kẻ Khờ | Blasphemy Slate: Phiến Đá Phỉ Báng]


[TIÊU ĐỀ CHƯƠNG GỐC]
{title}

[NỘI DUNG GỐC]
{text}
"""
    return prompt


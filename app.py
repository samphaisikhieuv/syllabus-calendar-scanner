import streamlit as st
from pdf2image import convert_from_bytes
from ocr_utils import extract_text_from_image
from date_utils import find_date_strings

st.title("Syllabus Calendar Scanner")

uploaded_file = st.file_uploader("Upload a syllabus PDF", type=["pdf"])

if uploaded_file is not None:
    st.success("PDF uploaded successfully!")
    st.write("File name:", uploaded_file.name)

    pdf_bytes = uploaded_file.read()
    pages = convert_from_bytes(pdf_bytes)

    st.write(f"Number of pages: {len(pages)}")

    all_results = []

    for page_number, page_image in enumerate(pages, start=1):
        st.subheader(f"Page {page_number}")
        st.image(page_image, caption=f"Page {page_number}")

        text = extract_text_from_image(page_image)
        st.text_area(f"OCR Text for Page {page_number}", text, height=200)

        dates = find_date_strings(text)

        if dates:
            st.write("Possible dates found:", dates)
            for date in dates:
                all_results.append({
                    "page": page_number,
                    "date": date,
                    "source_text": text
                })
        else:
            st.write("No dates found on this page.")

    st.subheader("All Found Dates")
    st.write(all_results)

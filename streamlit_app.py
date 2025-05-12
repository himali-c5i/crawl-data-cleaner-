import streamlit as st
import pandas as pd
import datetime
import re
import io

# === Cleaning Logic for Amazon ===
def clean_amazon_data(df):
    df.columns = df.columns.str.strip().str.lower()
    column_mapping = {
        'a-link-normal href': 'product_url',
        's-image src': 'image_url',
        'a-size-base-plus': 'product_title',
        'a-icon-alt': 'rating',
        'a-offscreen': 'list_price'
    }
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)
    required_columns = ['product_url', 'image_url', 'product_title', 'rating', 'list_price']
    df = df[[col for col in required_columns if col in df.columns]]
    df.dropna(subset=['product_url', 'product_title'], inplace=True)

    def parse_rating(val):
        if isinstance(val, str):
            match = re.search(r'([0-5]\.?\d*)', val)
            if match:
                return round(float(match.group(1)) * 2) / 2
        return None

    if 'rating' in df.columns:
        df['rating'] = df['rating'].apply(parse_rating)

    now = datetime.datetime.now()
    df['crawled_date'] = now
    df['week'] = now.isocalendar().week
    df['month'] = now.month
    df['quarter'] = (now.month - 1) // 3 + 1
    df['year'] = now.year

    def extract_retailer(url):
        if isinstance(url, str) and url.count('/') >= 3:
            return url.split('/')[2]
        return None

    def extract_product_code(url):
        if isinstance(url, str):
            match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url)
            if match:
                return match.group(1)
        return None

    df['retailer'] = df['product_url'].apply(extract_retailer)
    df['product_code'] = df['product_url'].apply(extract_product_code)
    df['product_description'] = df['product_title']
    df['stock_information'] = df['product_url'].apply(
        lambda x: "In Stock" if isinstance(x, str) and "amazon" in x.lower() else "Out of Stock"
    )

    return df[[ 'product_url', 'product_code', 'product_title', 'image_url', 'rating',
                'list_price', 'product_description', 'stock_information',
                'crawled_date', 'week', 'month', 'quarter', 'year', 'retailer']]

# === Cleaning Logic for Walmart ===
def extract_rating_reviews(text):
    rating, reviews = None, None
    if isinstance(text, str):
        rating_match = re.search(r"([\d.]+)\s+out of 5 stars", text)
        reviews_match = re.search(r"(\d+)\s+reviews", text)
        if rating_match:
            rating = float(rating_match.group(1))
        if reviews_match:
            reviews = int(reviews_match.group(1))
    return pd.Series([rating, reviews])

def extract_product_code(url):
    if isinstance(url, str):
        match = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def safe_convert_price(value):
    try:
        if isinstance(value, str):
            value = value.replace("$", "").strip()
        return float(value)
    except:
        return None

def clean_walmart_data(df):
    if df.iloc[0].astype(str).str.contains("promo_price", case=False, na=False).any():
        df = df.iloc[1:].reset_index(drop=True)
    cleaned = pd.DataFrame()
    cleaned["product_url"] = df.get("w-100 href")
    cleaned["product_title"] = df.get("w_q67L")
    cleaned["image_url"] = df.get("absolute src")
    cleaned["promo"] = df.get("mr1").apply(safe_convert_price)
    cleaned[["rating", "reviews"]] = df.get("w_q67L 3").apply(extract_rating_reviews)
    cleaned["product_code"] = cleaned["product_url"].apply(extract_product_code)

    now = datetime.datetime.now()
    cleaned["product_description"] = cleaned["product_title"]
    cleaned["stock_status"] = cleaned["promo"].apply(lambda x: "In Stock" if pd.notnull(x) else "Out of Stock")
    cleaned["date"] = now
    cleaned["week"] = now.isocalendar().week
    cleaned["month"] = now.month
    cleaned["quarter"] = (now.month - 1) // 3 + 1
    cleaned["year"] = now.year
    cleaned["retailer"] = "Walmart"
    return cleaned

# === Cleaning Logic for Mercado ===
def clean_mercado_data(df):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

    if 'product_url' not in df.columns:
        st.error("Missing 'product_url' column in the Mercado file.")
        return pd.DataFrame()

    df = df[df['product_url'].astype(str).str.contains('MLB', na=False)]

    df['product_code'] = df['product_url'].apply(
        lambda x: next((part for part in str(x).split('/') if part.startswith('MLB')), None)
    )

    # Clean promo_price (already extracted in the file)
    df['promo_price'] = df['promo_price'].astype(str).str.extract(r'(\d+)')[0]
    df['promo_price'] = df['promo_price'].fillna('0').astype(float)

    df['list_price'] = df['promo_price']

    if 'review' in df.columns:
        df['review'] = df['review'].astype(str).str.extract(r'(\d+)')[0]
        df['review'] = pd.to_numeric(df['review'], errors='coerce')

    if 'rating' in df.columns:
        df['rating'] = df['rating'].astype(str).str.extract(r'(\d+\.?\d*)')[0]
        df['rating'] = pd.to_numeric(df['rating'], errors='coerce')

    if 'discount' in df.columns:
        df['discount'] = df['discount'].astype(str).str.extract(r'(\d+%)')[0]

    now = datetime.datetime.now()
    df['date'] = now
    df['week'] = now.isocalendar().week
    df['month'] = now.month
    df['quarter'] = (now.month - 1) // 3 + 1
    df['year'] = now.year

    return df[[ 'product_url', 'product_code', 'product_title', 'image_url',
                'rating', 'review', 'promo_price', 'list_price', 'discount',
                'date', 'week', 'month', 'quarter', 'year' ]]

# === Streamlit App ===
st.title("Crawl Data Cleaner")
st.markdown("Upload a crawl file and select the retailer to clean the data accordingly.")

retailer_option = st.selectbox("Select Retailer", ["Amazon", "Mercado", "Walmart"])
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file and retailer_option:
    try:
        df_input = pd.read_excel(uploaded_file, header=1 if retailer_option == "Mercado" else 0)
        if st.button("Clean Data"):
            if retailer_option == "Amazon":
                cleaned = clean_amazon_data(df_input)
            elif retailer_option == "Mercado":
                cleaned = clean_mercado_data(df_input)
            elif retailer_option == "Walmart":
                cleaned = clean_walmart_data(df_input)

            if cleaned is not None and not cleaned.empty:
                st.success("Data cleaned successfully.")
                st.dataframe(cleaned.head())
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    cleaned.to_excel(writer, index=False, sheet_name="Cleaned Data")
                output.seek(0)
                st.download_button(
                    label="Download Cleaned File",
                    data=output,
                    file_name=f"{retailer_option.lower()}_cleaned_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Cleaning returned no data. Please check the file format or contents.")
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")

        output.seek(0)
        st.download_button(
            label="Download Cleaned File",
            data=output,
            file_name="cleaned_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

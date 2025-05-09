import streamlit as st
import pandas as pd
import datetime
import re
import io

# Amazon cleaning logic
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
    return df[[
        'product_url', 'product_code', 'product_title', 'image_url', 'rating',
        'list_price', 'product_description', 'stock_information',
        'crawled_date', 'week', 'month', 'quarter', 'year', 'retailer']]

# Mercado cleaning logic
def clean_mercado_data(df):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    df = df[df['product_url'].astype(str).str.contains('MLB')]
    df['product_code'] = df['product_url'].apply(
        lambda x: next((part for part in x.split('/') if part.startswith('MLB')), None) if isinstance(x, str) else None
    )
    df['promo_price'] = df[df.columns[0]].astype(str).str.extract(r'(\d+)')[0]
    df['promo_price_cents'] = df[df.columns[2]].astype(str).str.extract(r'(\d+)')[0]
    df['promo_price'] = df['promo_price'].fillna('0') + '.' + df['promo_price_cents'].fillna('00')
    df['promo_price'] = df['promo_price'].apply(lambda x: float(x) if re.match(r'^\d+\.\d+$', x) else None)
    df['list_price'] = df['promo_price']
    df['review'] = df['review'].astype(str).str.extract(r'(-?\d+)')
    df['review'] = df['review'].astype(float).abs()
    df['rating'] = df['rating'].astype(str).str.extract(r'(\d+\.?\d*)')[0]
    df['rating'] = df['rating'].astype(float)
    df['discount'] = df['discount'].astype(str).str.extract(r'(\d+%)')
    now = datetime.datetime.now()
    df['date'] = now
    df['week'] = now.isocalendar().week
    df['month'] = now.month
    df['quarter'] = (now.month - 1) // 3 + 1
    df['year'] = now.year
    return df[[
        'product_url', 'product_code', 'product_title', 'image_url',
        'rating', 'review', 'promo_price', 'list_price', 'discount',
        'date', 'week', 'month', 'quarter', 'year']]

# Walmart cleaning logic
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
    cleaned["product_url"] = df["w-100 href"]
    cleaned["product_title"] = df["w_q67L"]
    cleaned["image_url"] = df["absolute src"]
    cleaned["promo"] = df["mr1"].apply(safe_convert_price)
    cleaned[["rating", "reviews"]] = df["w_q67L 3"].apply(extract_rating_reviews)
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

# Streamlit UI
st.title("Crawl Data Cleaner")
st.markdown("Upload crawl file and choose the retailer to clean the data accordingly.")

retailer_option = st.selectbox("Select Retailer", ["Amazon", "Mercado", "Walmart"])
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file and retailer_option:
    df_input = pd.read_excel(uploaded_file)
    if st.button("Clean Data"):
        if retailer_option == "Amazon":
            cleaned = clean_amazon_data(df_input)
        elif retailer_option == "Mercado":
            cleaned = clean_mercado_data(df_input)
        elif retailer_option == "Walmart":
            cleaned = clean_walmart_data(df_input)
        st.success("Data cleaned successfully.")
        st.dataframe(cleaned.head())
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            cleaned.to_excel(writer, index=False, sheet_name="Cleaned Data")
        output.seek(0)
        st.download_button(
            label="Download Cleaned File",
            data=output,
            file_name="cleaned_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

## Get API Key

1. **Create an eBird account** (if you don’t already have one):  
   - Go to [https://ebird.org](https://ebird.org) and sign up.

2. **Request an API key**:  
   - Go to [eBird API documentation](https://documenter.getpostman.com/view/664302/ebird-api-20/2HTbHW).  
   - Scroll to “Request an API key” or visit [https://ebird.org/api/key](https://ebird.org/api/key).  
   - Fill in the form with your account info and intended use.

3. **Wait for approval**:  
   - The key is usually issued immediately or within a short time.  
   - You will receive a string like `abcd1234efgh5678` — this is your API key.

4. **Create a `.env` file** under the root directory with the format:  
   ```bash
   EBIRD_API_KEY=your_api_key
   ```

## Steps to running
1.  Run `docker compose build --no-cache airflow`
2.  Run `docker compose up airflow`

To check airflow outputs - view the [8080 localhost.](http://localhost:8080/)

UN: admin

PW: admin

## 🌐 Live Demo

Try the deployed Streamlit app here:  
 **https://ebird-data-analysis-79q4xqgr2x6fgjkgfonpzs.streamlit.app**

This app allows you to explore recent bird observations, hotspot distributions, and species-level patterns using the eBird API.

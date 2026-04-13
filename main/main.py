## ***Main libs***

import os,re,threading,requests,tkinter as tk
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from bs4 import BeautifulSoup
from tkinter import ttk, filedialog, messagebox

SEARCH_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


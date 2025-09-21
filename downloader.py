import os
import re
import time
import shutil
import requests
from bs4 import BeautifulSoup
from PIL import Image

# ================== 配置 ==================
BASE_URL = "https://drm.lib.pku.edu.cn"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}
TEMP_DIR = "temp"
COOKIE = ""

def parse_cookie(cookie_str):
    cookies = {}
    for item in cookie_str.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies[k] = v
    return cookies

# ================== 第一步 获取页面信息 ==================
def get_paper_info(fid, cookies):
    url = f"{BASE_URL}/pdfindex1.jsp?fid={fid}"
    print(f"[Step 1] 请求论文信息页面: {url}")
    resp = requests.get(url, cookies=cookies, headers=HEADERS)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    info = {}
    for tag in ["infoname", "filename", "startpage", "endpage", "fid"]:
        element = soup.find("input", {"id": tag})
        if element:
            info[tag] = element.get("value")

    print("[Step 1] 获取到论文信息:", info)
    return info

# ================== 第二步 获取所有页图片地址 ==================
def get_all_image_urls(info, cookies):
    start = int(info["startpage"])
    end = int(info["endpage"])
    fid = info["fid"]
    filename = info["filename"]

    img_urls = {}

    print(f"[Step 2] 开始获取图片地址，总页数 {end}")
    page = start
    while page <= end - 2: # 当前页码 <= end - 5
        urls = fetch_page_group(page, fid, filename, cookies)
        for u in urls:
            img_urls[u["id"]] = u["src"]
        page += 3

    # 单独请求一次最后的 end-2
    urls = fetch_page_group(end - 2, fid, filename, cookies)
    for u in urls:
        img_urls[u["id"]] = u["src"]

    # 按页码排序
    ordered = [img_urls[str(i)] for i in range(end)]
    print(f"[Step 2] 共获取到 {len(ordered)} 页图片链接")
    return ordered

def fetch_page_group(page, fid, filename, cookies):
    url = f"{BASE_URL}/jumpServlet?page={page}&fid={fid}&userid=&filename={filename}&visitid="
    print(f"  -> 请求 jumpServlet: page={page}")

    for attempt in range(5):
        try:
            resp = requests.get(url, cookies=cookies, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data["list"]
        except Exception as e:
            print(f"  !! 请求失败 page={page}, 错误: {e} (第{attempt+1}次)")
            time.sleep(1)

    print(f"  !! 最终失败，跳过 page={page}")
    return []


# ================== 第三步 下载图片 ==================
def download_images(urls, cookies):
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
    
    print(f"[Step 3] 开始下载 {len(urls)} 张图片...")
    for i, url in enumerate(urls):
        img_path = os.path.join(TEMP_DIR, f"{i}.jpeg")

        if os.path.exists(img_path):
            print(f"  -> 已存在 {i+1}/{len(urls)}: {img_path}，跳过下载")
            continue

        success = False
        for attempt in range(5):
            retry_param = int(time.time() * 1000)
            img_url = f"{url}&_retry={retry_param}"

            try:
                resp = requests.get(img_url, cookies=cookies, headers=HEADERS, stream=True, timeout=10)
                if resp.status_code == 200:
                    with open(img_path, "wb") as f:
                        for chunk in resp.iter_content(1024):
                            f.write(chunk)
                    print(f"  -> 已下载 {i+1}/{len(urls)}: {img_path}")
                    success = True
                    break
                else:
                    print(f"  !! 下载失败 页码 {i}, 状态码 {resp.status_code} (第{attempt+1}次)")
            except Exception as e:
                print(f"  !! 请求异常 页码 {i}, 错误: {e} (第{attempt+1}次)")

            time.sleep(1)

        if not success:
            print(f"  !! 最终失败，跳过 页码 {i}")

    print("[Step 3] 图片下载完成")

# ================== 第四步 组合 PDF ==================
def images_to_pdf(info):
    pdf_name = f"{info['infoname']}_{info['fid']}.pdf"
    pdf_path = os.path.join(os.getcwd(), pdf_name)

    print(f"[Step 4] 开始合成 PDF: {pdf_name}")
    files = [os.path.join(TEMP_DIR, f"{i}.jpeg") for i in range(int(info["endpage"]))]

    images = [Image.open(f).convert("RGB") for f in files]
    if images:
        images[0].save(pdf_path, save_all=True, append_images=images[1:])
        print(f"[Step 4] PDF 合成成功: {pdf_path}")
    else:
        print("  !! 没有找到图片，PDF 未生成")

    # 清理临时文件夹
    shutil.rmtree(TEMP_DIR)
    print("[Step 4] 已删除临时文件夹")

# ================== 主流程 ==================
if __name__ == "__main__":
    cookie_str = (input("请输入Cookie: ") or COOKIE).strip()
    cookies = parse_cookie(cookie_str)
    while True:
        fid = input("请输入论文 fid: ").strip()
        info = get_paper_info(fid, cookies)
        urls = get_all_image_urls(info, cookies)
        download_images(urls, cookies)
        images_to_pdf(info)


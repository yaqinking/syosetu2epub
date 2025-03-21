import urllib.request
from bs4 import BeautifulSoup

import os
import shutil
import zipfile
import tempfile
import sys
import string
from datetime import datetime
import requests
import pytz
import urllib
import urllib3
from html import escape

urllib3.disable_warnings()
cwd = os.getcwd()
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

compact = False
horizontal_class = ''
page_direction = 'rtl'
min_chapter = 0
max_chapter = 100000000

class Novel:
    def __init__(self, link: str):
        global min_chapter
        global max_chapter
        
        self.chapterCount = 0
        self.link = link
        if self.link[-1] == "/":
            self.link = self.link[:-1]
        self.page = BeautifulSoup(SyosetuRequest(link).getPage(), 'html.parser')
        self.seriesCode = link.split(".syosetu.com/", 1)[1]

        # get TOC page count
        self.tocPageCount = 1
        a_tag = self.page.find(class_="c-pager__item--last")
        if a_tag:
            self.tocPageCount = int(a_tag["href"].split('=')[1])

        # get author, title
        self.title = self.page.find(class_="p-novel__title").text
        self.title = "".join(c for c in self.title if c.isalnum() or c in " 【】「」").rstrip()
        self.title = escape(self.title)
        self.author = self.page.find(class_="p-novel__author").text.split('：', 1)[1]

        self.tocInsert = ""
        self.tocInsertLegacy = ""

        pages = [self.page]
        i = 2
        while i <= self.tocPageCount:
            pages.append(BeautifulSoup(SyosetuRequest(self.link + "/?p=" + str(i)).getPage(), 'html.parser'))
            i += 1

        tocInsert = ""
        tocInserted = ""
        
        for page in pages:
            if self.chapterCount > max_chapter:
                break
            
            indexBox = page.find(class_="p-eplist")
            for item in indexBox.find_all(["div", "a"]):
                class_name = item.get("class")[0]
                if "chapter-title" in class_name:
                    tocInsert = "<li><span>" + escape(item.contents[0]) + "</span></li>\n"
                elif "subtitle" in class_name:
                    title = escape(item.contents[0])
                    self.chapterCount += 1
                    
                    if self.chapterCount < min_chapter:
                        continue
                    if self.chapterCount > max_chapter:
                        break
                        
                    if tocInsert != tocInserted:
                        self.tocInsert += tocInsert
                        tocInserted = tocInsert
                    
                    self.tocInsert += "<li><a href=\"" + str(self.chapterCount) + ".xhtml\">" + title + "</a></li>\n"
                    self.tocInsertLegacy += "<navPoint id=\"toc" + str(self.chapterCount) + "\" playOrder=\"" + str(
                        self.chapterCount) + "\"><navLabel><text>" + title + "</text></navLabel><content src=\"" + str(self.chapterCount) + ".xhtml\"/></navPoint>"
        
        if self.chapterCount < max_chapter:
            max_chapter = self.chapterCount
        
    def build(self):
        tempDir = tempfile.TemporaryDirectory()
        shutil.copytree(os.path.join(__location__, 'template'), os.path.join(tempDir.name, self.title))
        os.mkdir(os.path.join(tempDir.name, self.title, "images"))

        imgCount = 0

        def adjust(root) -> str:
            nonlocal imgCount
            for item in root.find_all('a'):
                if item.get('href') and "https://" not in item['href']:
                    item['href'] = "https://" + item['href'].split("//", 1)[1]
            for item in root.find_all('img'):
                src = item.get('src')
                if item.get('src'):
                    src = "https:" + src
                r = requests.get(src, allow_redirects=True)
                open(os.path.join(tempDir.name, self.title, 'images', str(imgCount) + '.jpg'), 'wb').write(r.content)
                item['src'] = "../images/" + str(imgCount) + ".jpg"
                imgCount += 1
            if compact:
                for item in root.find_all('br'):
                    item.decompose()

            return root.prettify()

        # THE FOLLOWING WRITES THE COMPLETE TABLE OF CONTENTS AND TITLE PAGE FILES
        with open(os.path.join(__location__, 'files/nav.xhtml'), encoding="utf-8") as t:
            template = string.Template(t.read())
            finalOutput = template.substitute(TITLETAG=self.title, TOCTAG=self.tocInsert, HTMLCLASS=horizontal_class)
            oebpsDir = os.path.join(tempDir.name, self.title, "OEBPS")
            with open(os.path.join(oebpsDir, "nav.xhtml"), "w", encoding="utf-8") as output:
                output.write(finalOutput)
        with open(os.path.join(__location__, 'files/toc.ncx'), encoding="utf-8") as t:
            template = string.Template(t.read())
            finalOutput = template.substitute(IDTAG=self.seriesCode, TITLETAG=self.title, TOCTAG=self.tocInsertLegacy)
            oebpsDir = os.path.join(tempDir.name, self.title, "OEBPS")
            with open(os.path.join(oebpsDir, "toc.ncx"), "w", encoding="utf-8") as output:
                output.write(finalOutput)
        with open(os.path.join(__location__, 'files/titlepage.xhtml'), encoding="utf-8") as t:
            template = string.Template(t.read())
            finalOutput = template.substitute(TITLETAG=self.title, AUTHORTAG="作者: " + self.author)
            oebpsDir = os.path.join(tempDir.name, self.title, "OEBPS")
            with open(os.path.join(oebpsDir, "titlepage.xhtml"), "w", encoding="utf-8") as output:
                output.write(finalOutput)

        # THE FOLLOWING GETS ALL THE CHAPTERS
        chapterList = ""
        chapterListSpine = ""
        for i in range(self.chapterCount):
            if i < min_chapter - 1 or i > max_chapter - 1:
                continue
            
            print(f"Downloading chapter {i + 1}/{max_chapter}")
            thisChapter = BeautifulSoup(SyosetuRequest(self.link + "/" + str(i+1)).getPage(), 'html.parser')
            title = thisChapter.find(class_="p-novel__title").text
            title = escape(title)
            chapterText = "<h2 id=\"toc_index_1\">" + title + "</h2>\n"

            sectionTexts = [adjust(text) for text in thisChapter.find_all(class_="js-novel-text")]
            chapterText += "<hr/>\n".join(sectionTexts)

            with open(os.path.join(__location__, 'files/chaptertemplate.xhtml'), encoding="utf-8") as t:
                template = string.Template(t.read())
                finalOutput = template.substitute(TITLETAG=title, BODYTAG=chapterText, HTMLCLASS=horizontal_class)
                with open(os.path.join(tempDir.name, self.title, 'OEBPS', (str(i + 1) + '.xhtml')), "w", encoding="utf-8") as output:
                    output.write(finalOutput)
            chapterList += "<item media-type=\"application/xhtml+xml\" href=\"" + \
                str(i + 1) + ".xhtml""\" id=\"_" + str(i + 1) + ".xhtml\" />"
            chapterListSpine += "<itemref idref=\"_" + str(i + 1) + ".xhtml\" />"

        with open(os.path.join(__location__, 'files/content.opf'), encoding="utf-8") as t:
            template = string.Template(t.read())
            finalOutput = template.substitute(IDTAG=self.seriesCode, TITLETAG=self.title, AUTHORTAG=self.author, TIMESTAMPTAG=datetime.now(
                pytz.utc).isoformat().split('.', 1)[0] + 'Z', CHAPTERSTAG=chapterList, SPINETAG=chapterListSpine, PAGEDIRECTION=page_direction)
            oebpsDir = os.path.join(tempDir.name, self.title, "OEBPS")
            with open(os.path.join(oebpsDir, "content.opf"), "w", encoding="utf-8") as output:
                output.write(finalOutput)

        # zip up all items and rename .zip to .epub
        outputPath = os.path.join(cwd, self.title)
        appendage = ""
        i = 1
        while os.path.isfile(outputPath + appendage + '.epub'):
            appendage = "(" + str(i) + ")"
            i += 1
        outputPath = outputPath + appendage + '.epub'

        with zipfile.ZipFile(outputPath, 'w') as zip:
            os.chdir(os.path.join(__location__, 'files'))
            zip.write('mimetype')
            os.chdir(os.path.join(tempDir.name, self.title))
            paths = []
            for root, _, files in os.walk('.'):
                for filename in files:
                    path = os.path.join(root, filename)
                    paths.append(path)
            for doc in paths:
                zip.write(doc)
            os.chdir(__location__)


class SyosetuRequest:
    def __init__(self, link: str):
        self.srHeaders = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15'
        }
        self.srCookies = dict(over18='yes')
        self.link: str = link
        r = requests.get(url=self.link, headers=self.srHeaders, cookies=self.srCookies, proxies=urllib.request.getproxies(), verify=False)
        if not r.text:
            raise Exception("Unable to get response from " + link)
        self.page = r.text

    def getPage(self) -> str:
        return self.page


if __name__ == "__main__":
    link: str = None
    skip_next = False
    
    for i, arg in enumerate(sys.argv):
        if skip_next:
            skip_next = False
            continue
        
        if ".syosetu.com/" in arg:
            link = arg
        if "-c" in arg:
            compact = True
        if "--horizontal" in arg:
            horizontal_class = 'horizontal'
            page_direction = 'ltr'
        if "--min" in arg:
            if i + 1 < len(sys.argv) and str.isdigit(sys.argv[i + 1]):
                min_chapter = int(sys.argv[i + 1])
                skip_next = True
            else:
                print("Error: No min_chapter found after --min.")
                os._exit(0)
        if "--max" in arg:
            if i + 1 < len(sys.argv) and str.isdigit(sys.argv[i + 1]):
                max_chapter = int(sys.argv[i + 1])
                skip_next = True
            else:
                print("Error: No min_chapter found after --max.")
                os._exit(0)
                
        if arg == "-h" or arg == "--Help" or arg == "--help":
            print("USAGE: syosetu2epub https://*.syosetu.com/******")
            print("OUTPUT: EPUB formatted ebook will be generated in current working directory")
            print("`-c`: Syosetu.com adds large spacing between blocks of text via br tags, which may greatly reduce the amount of words per page shown. Use `-c` to enable compact mode and ignore these spacers.")
            print("`--min`: Minimum chapter to start downloading from.")
            print("`--max`: Maximum chapter to download until.")
            print("`--horizontal`: Displays text horizontally instead of vertically. Scrolling between pages will also be from left to right instead of right to left.")
            os._exit(0)

    if link == None:
        print("USAGE: syosetu2epub https://*.syosetu.com/******")
        print("HELP: syosetu2epub -h")
        print("OUTPUT: EPUB formatted ebook will be generated in current working directory")
        os._exit(0)

    print("Downloading and building ebook. This may take a while depending on number of chapters and images")
    Novel(link).build()

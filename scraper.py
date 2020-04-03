from urllib.request import urlopen
import requests
import timesched,time, logging
from bs4 import BeautifulSoup
from bs4.element import ResultSet

logging.basicConfig(
    handlers=[logging.FileHandler('scraper.log'),logging.StreamHandler()],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

pttDomain = 'https://www.ptt.cc/bbs/{}'
header = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36'
NO_NEW_POST = 'No new post'
def getNewPosts(boardname:str, lastTimeScraped: str= ""):
    scrapedtime = 0
    # 整理成 List
    try:
        bs = getBSObj(pttDomain.format(boardname + '/index.html'))
        # 如果回傳例外，丟回給 Bot 輸出
        if isinstance(bs,Exception):
            return ({'success':False, 'error': bs})
        
        doneScraped = False
        newpostList = []
        posts = bs.find(class_='r-list-sep').find_previous_siblings(class_='r-ent')

        while not doneScraped:
            if scrapedtime >10 : 
                return({'success':False, 'error':'可能進入迴圈，中斷作業'})
            
            doneScraped, templist = scrap(lastTimeScraped, posts)
            newpostList = templist + newpostList
            bs = getBSObj(pttDomain.format(getPrevPageLink(bs)))
            posts = reversed(bs.find_all(class_='r-ent')) # PTT 的最新文章由下往上
            print(type(posts))
            time.sleep(.5)
            scrapedtime+=1

    except requests.exceptions.HTTPError as e:
        return({'success':False, 'error':str(e.response)})
    except ValueError:
        # 找無最後存取值，輸出最新文章
        lastTimeScraped = ""
        doneScraped, templist = scrap(lastTimeScraped, posts)
        return({'success':True, 'posts': templist,'error':'找無最後存取值，輸出最新文章'})
    
    # 預期結果時的輸出
    if newpostList:
        return({'success':True, 'posts': newpostList})
    else:
        return({'success':True, 'posts': NO_NEW_POST})

def getBSObj(link:str):
    try:
        html = requests.get(link,header,cookies={'over18':'1'})
        html.raise_for_status()
        bs = BeautifulSoup(html.text,'html.parser')

        return bs
    except requests.exceptions.HTTPError as e:
        return e

def scrap(lastTimeScraped:str, posts):
    newpostList = []
    doneScraped = False
    if lastTimeScraped:
        # 檢查最後存取值是否還在文章列表中
        tempbs = getBSObj(pttDomain.format(lastTimeScraped.replace('/bbs/',"")))
        if not isinstance(tempbs, Exception):
            for post in posts:
                titleItem = post.find(class_='title')
                # 檢查最新貼文與上次是否相同
                try:
                    if lastTimeScraped == titleItem.a.get('href'):
                        doneScraped = True
                        break
                    else:
                        newpostList.insert(0, {'title':titleItem.a.get_text(), 'url':titleItem.a.get('href')})
                except AttributeError as e: # A post may be deleted, skip this post
                    logging.info(str(e))
                    continue
        else:
            print(pttDomain.format(lastTimeScraped) + 'Not exist?')
            raise ValueError
    else:
        doneScraped = True
        try:
            titleItem = posts[0].find(class_='title')
            newpostList.insert(0, {'title':titleItem.a.get_text(), 'url':titleItem.a.get('href')})
        except IndexError as e:
            print(e)
            
    return doneScraped, newpostList

def getPrevPageLink(bs:BeautifulSoup):
    try:
        prevPageLink = str(bs.select('.btn-group-paging>a')[1].get('href'))
        return prevPageLink.replace('/bbs/',"")
    except IndexError as e:
        print("selector error:{}".format(e))

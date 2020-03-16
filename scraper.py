from urllib.request import urlopen
import requests
import timesched,time
from bs4 import BeautifulSoup

ptt = 'https://www.ptt.cc/bbs/{}/index.html'
header = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36'

def getNewPost(boardname:str):
    try:
        html = requests.get(ptt.format(boardname),header)
        html.raise_for_status()
        bs = BeautifulSoup(html.text,'html.parser')

        lateset = bs.find(class_='r-list-sep').find_previous_sibling()
        titleItem = lateset.find(class_='title')

        return({'status':True, 'title':titleItem.a.get_text(), 'url':titleItem.a.get('href')})
    except requests.exceptions.HTTPError as e:
        return({'status':False, 'title':str(e.response)})

    
# boardname = input("輸入看板")
# s = timesched.Scheduler(time.time,time.sleep)
# s.repeat(5,0,getTopicList,boardname)
# s.run()
from telegram.ext import Updater, CallbackContext, Job, CommandHandler, MessageHandler,CallbackQueryHandler , Filters
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from time import time
from datetime import timedelta
import configparser, os, pickle, logging
import pytimeparse, timesched, redis
import scraper

logging.basicConfig(
    handlers=[logging.FileHandler('telegram.log'),logging.StreamHandler()],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)


config = configparser.ConfigParser()
config.read('config.ini')

MINUTE = 60
DEFAULT_INTEVAL = int(os.environ.get('INTEVAL','15'))
MAX_JOB_PER_ID = 4

WELCOME_PHASE = """這裏是 PTT 新文章檢查小幫手，請使用
**/check \[看板]** \[_時間(可選)_] \[_排除詞(可選)_] 下達檢查指令，
時間預設 60 分鐘檢查一次，排除詞格式為 (term1/term2/...)
"""
POST_ITEM_TEMPLATE = "{}\nhttps://www.ptt.cc{}\n\n"

# TODO: refactor code
# TODO: all input convert to lowercase

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=WELCOME_PHASE, parse_mode=ParseMode.MARKDOWN)

# TODO: avoid flood 

JOB_DATA = ('callback', 'interval', 'repeat', 'context', 'days', 'name', 'tzinfo')
JOB_STATE = ('_remove', '_enabled')

# These snippet is copyed from package's wiki, modified to save on redis
# https://github.com/python-telegram-bot/python-telegram-bot/wiki/Code-snippets#save-and-load-jobs-using-pickle

def load_jobs(jq):
    while True:
        if redis_pool.exists('pickle'):
            next_t, data, state = pickle.loads(redis_pool.lpop('pickle'))
        else:
            break  # loaded all jobs

        # New object with the same data
        job = Job(**{var: val for var, val in zip(JOB_DATA, data)})

        # Restore the state it had
        for var, val in zip(JOB_STATE, state):
            attribute = getattr(job, var)
            getattr(attribute, 'set' if val else 'clear')()

        job.job_queue = jq
        next_t -= time()  # convert from absolute to relative time

        jq._put(job, next_t)

def save_jobs(jq):
    with jq._queue.mutex:  # in case job_queue makes a change

        if jq:
            job_tuples = jq._queue.queue
        else:
            job_tuples = []

        # reset the key
        logging.debug('Try to save jobs:')
        try:
            redis_pool.delete('pickle')

            for next_t, job in job_tuples:

                # This job is always created at the start
                if job.name == 'save_jobs_job':
                    continue

                # Threading primitives are not pickleable
                data = tuple(getattr(job, var) for var in JOB_DATA)
                state = tuple(getattr(job, var).is_set() for var in JOB_STATE)

                # Pickle the job
                # RPUSH(item1), place item1 at rightmost of the list -> 'item0' - 'item1'
                redis_pool.rpush('pickle', pickle.dumps((next_t, data, state))) 
                logging.debug(f'{job.name} {job.removed}')
        except AttributeError:
            logging.info('Redis may not inited?')


def save_jobs_job(context):
    save_jobs(context.job_queue)

def extBoardName(jobname: str):
    return jobname.partition('.')[2]

def extUserId(jobname: str):
    return int(jobname.partition('.')[0])

# Using extra list to organize user's jobs
# Iterate every job in JobQueue to append to list
def tidyup_jobs():
    for job in jobq.jobs():
        # This job is always created at the start
        if job.name == 'save_jobs_job': continue
        if job.removed: continue

        logging.info(f'Read job: {job.name}, Removed? {job.removed}')
        user_list = joblist_retrieve(extUserId(job.name))
        user_list.append(job)

def post_check(context: CallbackContext):
    scarp_args = context.job.context

    new_scrap = scraper.getNewPosts(extBoardName(context.job.name), scarp_args['prev'])

    logging.info("Now running: {}".format(context.job.name))
    
    if new_scrap['success']: 
        if new_scrap['posts'] == scraper.NO_NEW_POST:
            return
        if 'error' in new_scrap:
            context.bot.send_message(chat_id=scarp_args['id'], text= new_scrap['error'])
        output_str = ""
        for post in new_scrap['posts']:
            termMatch = False
            # 各種條件過濾

            if '[公告]' in post['title']:
                termMatch = True
            if 'exclude' in scarp_args:
                for term in scarp_args['exclude']:
                    if term in post['title']:
                        termMatch = True
            if not termMatch:
                output_str += POST_ITEM_TEMPLATE.format(post['title'],post['url'])

        scarp_args['prev'] = new_scrap['posts'][-1]['url']
        if output_str:
            context.bot.send_message(chat_id=scarp_args['id'], text=output_str)
    else:
        context.job.schedule_removal()
        remove_from_joblist(context.job.name)
        context.bot.send_message(
            chat_id = scarp_args['id'], 
            text= ''.join([new_scrap['error'],"\n看板名輸入有誤，請檢查並重新輸入"]))

# TODO:過濾不正確參數 / error handling 
def callback_post_set(update:Update, context: CallbackContext):
    # 最大任務數
    joblist = joblist_retrieve(update.effective_user.id)
    if  len(joblist)>= MAX_JOB_PER_ID:
        context.bot.send_message(chat_id=update.effective_chat.id, text="任務已滿")
        return

    # 不正確的參數就排除
    if not context.args or len(context.args)>3:
        context.bot.send_message(chat_id=update.effective_chat.id, text="請檢查參數是否輸入正確")
    # 由後依序處理參數
    else:
        for job in joblist:
            if str(context.args[0]).lower() == extBoardName(job.name):
                context.bot.send_message(chat_id=update.effective_chat.id, text="此任務已存在，若需更改條件請先移除原有任務")
                return
        input_interval = DEFAULT_INTEVAL*MINUTE
        scarp_args = {'id':update.effective_chat.id,'prev':''}
        if len(context.args) >1:
            if len(context.args)==3:
                excludeList = context.args[2].split('/')
                scarp_args.update({'exclude':excludeList})

            # 檢查數字輸入
            int_or_parse = (lambda x: int(x) if x.isdigit() else pytimeparse.parse(x)/60)
            input_interval = (lambda x:int(x*MINUTE) if x is not None and x > DEFAULT_INTEVAL and x <= 720 \
                else DEFAULT_INTEVAL*MINUTE)(int_or_parse(context.args[1]))

            if input_interval == DEFAULT_INTEVAL*MINUTE:
                context.bot.send_message(chat_id=update.effective_chat.id, text="使用預設檢查間隔")
        joblist.append(jobq.run_repeating(post_check, interval=input_interval,
                        first=0, context=scarp_args,name= (f'{update.effective_user.id}.{context.args[0]}')))  # args[0] = boardname
        logging.info(f'The interval of added job is :{input_interval} secs')
        context.bot.send_message(chat_id=update.effective_chat.id, text="任務已增加，可使用 /status 查詢狀態")

# if list empty > remove item in dict?
def callback_job_remove(update:Update, context: CallbackContext):
    # job.stop()
    keyboard = []
    for job in joblist_retrieve(update.effective_user.id):
        keyboard.append([InlineKeyboardButton(extBoardName(job.name), callback_data=job.name)])
    
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=update.effective_chat.id, text="選擇需撤回的任務",reply_markup=reply_markup)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text="尚無任務")

def callback_job_rm_selected(update:Update, context: CallbackContext):
    query = update.callback_query
    remove_from_joblist(query.data)

    query.edit_message_text(text="{} 已撤回".format(extBoardName(query.data)))

def callback_show_status(update:Update, context: CallbackContext):
    status_output = ""
    for current_job in joblist_retrieve(update.effective_user.id):
        exclude_term = "無" if not 'exclude' in current_job.context else current_job.context['exclude']
        status_output += (f"指定看板：{extBoardName(current_job.name)} \n"
        f"檢查間隔：{int(current_job.interval/60)} （分鐘）\n"
        f"排除關鍵字：{'/'.join(exclude_term)}\n"
        f"最後抓取值：https://www.ptt.cc{current_job.context['prev']}\n\n")
    if not status_output:
        status_output = "尚未安排任務"
    context.bot.send_message(chat_id=update.effective_chat.id, text= status_output)

# let this cmd stick to remove cmd
def callback_cancel(update:Update, context: CallbackContext):
    context.bot.edit_message_text('已取消')

def joblist_retrieve(user_id:int) -> list :
    if user_id not in track_job_dict:
        templist = list()
        track_job_dict.update({user_id:templist})
        return templist
    else:
        return track_job_dict[user_id]

def remove_from_joblist(jobname):
    joblist = joblist_retrieve(extUserId(jobname))
    for job in joblist:
        if job.name == jobname:
            job.schedule_removal()
            try:
                joblist_retrieve(extUserId(jobname)).remove(job)
            except ValueError as e:
                logging.info(str(e))


### Bot set-up ###

# Heroku using redis to make JobQueue being presistance 
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
redis_pool = redis.from_url(redis_url)
try:
    redis_pool.ping()
    logging.info('Redis server connected: {}'.format(redis_url[8:14]))
except redis.ConnectionError as e:
    logging.info(str(e.with_traceback))

# replace token you got
# Heroku webhook
TOKEN = os.environ.get('TOKEN',"")
PORT = int(os.environ.get('PORT','8443'))
if TOKEN :
    updater = Updater(token=TOKEN,use_context=True)  # which means on heroku
else:
    updater = Updater(token=config['dev']['token'],use_context=True) # local dev

dispatcher = updater.dispatcher
jobq = updater.job_queue
# Periodically save jobs
jobq.run_repeating(save_jobs_job, timedelta(minutes=1))
track_job_dict = dict() # Access by ID
try:
    load_jobs(jobq)
    tidyup_jobs()

except FileNotFoundError:
    # First run
    pass


start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

status_handler = CommandHandler('status', callback_show_status)
check_handler = CommandHandler('check', callback_post_set)
remove_handler = CommandHandler('remove',callback_job_remove)
cancel_handler = CommandHandler('cancel',callback_cancel)
job_select_handler = CallbackQueryHandler(callback_job_rm_selected)

dispatcher.add_handler(check_handler)
dispatcher.add_handler(remove_handler)
dispatcher.add_handler(cancel_handler)
dispatcher.add_handler(status_handler)
dispatcher.add_handler(job_select_handler)

if TOKEN:
    updater.start_webhook(listen="0.0.0.0",port=PORT,url_path=TOKEN)
    updater.bot.set_webhook("https://ptt-newpost-bot.herokuapp.com/"+TOKEN)
    updater.idle()

    save_jobs(jobq)

else:
    logging.info("Running local")
    updater.start_polling()


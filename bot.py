from telegram.ext import Updater,CallbackContext
from telegram import Update,ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
import configparser
import logging, pytimeparse
import scraper
from telegram.ext import CommandHandler, MessageHandler,CallbackQueryHandler , Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.DEBUG)

config = configparser.ConfigParser()
config.read('config.ini')

DEFAULT_INTEVAL = 10
MAX_JOB_PER_ID = 4

WELCOME_PHASE = """這裏是 PTT 新文章檢查小幫手，請使用
**/check \[看板]** \[_時間(可選)_] \[_排除詞(可選)_] 下達檢查指令，
時間預設 60 分鐘檢查一次，排除詞格式為 (term1/term2/...)
"""

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=WELCOME_PHASE, parse_mode=ParseMode.MARKDOWN)

# TODO: 維持關閉後記憶 / 改用 user_data 儲存資料？ / avoid flood 


# TODO: Ignore 公告
def callback_post_check(context: CallbackContext):
    scarp_args = context.job.context
    newly_scrap = scraper.getNewPost(context.job.name)

    logging.info("Job name is {}".format(context.job.name))
    
    if newly_scrap['status']: 

        # 檢查最新貼文與上次是否相同
        if scarp_args['prev'] == newly_scrap['url']:
            return
        # 檢查排除關鍵字
        elif 'exclude' in scarp_args:
            for term in scarp_args['exclude']:
                if term in newly_scrap['title']:
                    scarp_args['prev'] = newly_scrap['url']
                    return
        
        output_str = "{}\nhttps://www.ptt.cc{}"
        output_str = output_str.format(newly_scrap['title'],newly_scrap['url'])

        scarp_args['prev'] = newly_scrap['url']
        context.bot.send_message(chat_id=scarp_args['id'], text=output_str)
    else:
        context.job.schedule_removal()
        context.bot.send_message(
            chat_id = scarp_args['id'], 
            text= ''.join([newly_scrap['content'],"\n看板名輸入有誤，請檢查並重新輸入"]))
# TODO:過濾不正確參數 / error handling 
def callback_post_set(update:Update, context: CallbackContext):
    # 最大任務數
    joblist = joblist_retrieve(update.effective_chat.id)
    if  len(joblist)>= MAX_JOB_PER_ID:
        context.bot.send_message(chat_id=update.effective_chat.id, text="任務已滿")
        return

    # 不正確的參數就排除
    if not context.args or len(context.args)>3:
        context.bot.send_message(chat_id=update.effective_chat.id, text="請檢查參數是否輸入正確")

    # 由後依序處理參數
    else:
        input_interval = DEFAULT_INTEVAL
        scarp_args = {'id':update.effective_chat.id,'prev':''}
        if len(context.args) >1:
            excludeList = context.args[2].split('/') if len(context.args)==3 else None
            scarp_args.update({'exclude':excludeList})

            # 檢查數字輸入
            int_or_parse = (lambda x: int(x) if x.isdigit() else pytimeparse.parse(x))
            input_interval = (lambda x:(x*60) if x is not None and x > DEFAULT_INTEVAL else DEFAULT_INTEVAL)(int_or_parse(context.args[1]))
            if input_interval == DEFAULT_INTEVAL:
                context.bot.send_message(chat_id=update.effective_chat.id, text="使用預設檢查間隔")

        joblist.append(job.run_repeating(callback_post_check, interval=input_interval,
                         first=0, context=scarp_args,name= context.args[0]))  # args[0] = boardname
        logging.info(joblist_retrieve(update.effective_chat.id))
        context.bot.send_message(chat_id=update.effective_chat.id, text="任務已增加，可使用 /status 查詢狀態")

# if list empty > remove item in dict?
def callback_job_remove(update:Update, context: CallbackContext):
    # job.stop()
    keyboard = []
    for job in joblist_retrieve(update.effective_chat.id):
        keyboard.append([InlineKeyboardButton(job.name,callback_data=job.name)])
    
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=update.effective_chat.id, text="選擇需撤回的任務",reply_markup=reply_markup)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text="尚無任務")

def callback_job_rm_select(update:Update, context: CallbackContext):
    query = update.callback_query
    logging.info(update.effective_chat.id)
    joblist = joblist_retrieve(update.effective_chat.id)
    for job in joblist:
        if job.name == query.data:
            logging.info(f'{job.name} and {query.data}') 
            job.schedule_removal()
            try:
                joblist_retrieve(update.effective_chat.id).remove(job)
            except ValueError as e:
                logging.info(str(e))

    query.edit_message_text(text="{} 已撤回".format(query.data))

def callback_show_status(update:Update, context: CallbackContext):
    status_output = ""
    for current_job in joblist_retrieve(update.effective_chat.id):
        exclude_term = "無" if not 'exclude' in current_job.context else current_job.context['exclude']
        status_output += (f"指定看板：{current_job.name} \n"
        f"檢查間隔：{int(current_job.interval/60)} （分鐘）\n"
        f"排除關鍵字：{'/'.join(exclude_term)}\n"
        f"最後抓取值：https://www.ptt.cc{current_job.context['prev']}\n\n")
    if not status_output:
        status_output = "尚未安排任務"
    context.bot.send_message(chat_id=update.effective_chat.id, text= status_output)
def callback_cancel(update:Update, context: CallbackContext):
    context.bot.edit_message_text('已取消')

def joblist_retrieve(user_id:str) -> list :
    if user_id not in track_job_dict:
        templist = list()
        track_job_dict.update({user_id:templist})
        return templist
    else:
        return track_job_dict[user_id]

### Bot set-up ###

# replace token you got
updater = Updater(token=config['telegram-bot']['token'],use_context=True)

dispatcher = updater.dispatcher
job = updater.job_queue
track_job_dict = dict() # Access by ID

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

status_handler = CommandHandler('status', callback_show_status)
check_handler = CommandHandler('check', callback_post_set)
remove_handler = CommandHandler('remove',callback_job_remove)
cancel_handler = CommandHandler('cancel',callback_cancel)
job_select_handler = CallbackQueryHandler(callback_job_rm_select)

dispatcher.add_handler(check_handler)
dispatcher.add_handler(remove_handler)
dispatcher.add_handler(cancel_handler)
dispatcher.add_handler(status_handler)
dispatcher.add_handler(job_select_handler)

updater.start_polling()
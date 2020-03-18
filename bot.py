from telegram.ext import Updater,CallbackContext
from telegram import Update
import configparser
import logging, pytimeparse
import scraper
from telegram.ext import CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.DEBUG)

config = configparser.ConfigParser()
config.read('config.ini')

DEFAULT_INTEVAL = 10
MAX_JOB_PER_ID = 4

# TODO:修改歡迎詞
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

def callback_post_check(context: CallbackContext):
    scarp_args = context.job.context
    newly_scrap = scraper.getNewPost(scarp_args['boardname'])
    
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
        #TODO: 完善敘述
        context.bot.send_message(
            chat_id = scarp_args['id'], 
            text= ''.join([newly_scrap['content'],"\ncheck input"]))
# TODO:過濾不正確參數 / error handling / 過濾重複看板(boardname as job name)
def callback_post_set(update:Update, context: CallbackContext):
    # 最大任務數
    joblist = joblist_retrieve(update.effective_chat.id)
    if  len(joblist)>= MAX_JOB_PER_ID:
        context.bot.send_message(chat_id=update.effective_chat.id, text="job full")
        return

    # 不正確的參數就排除
    if not context.args or len(context.args)>3:
        context.bot.send_message(chat_id=update.effective_chat.id, text="check args.")

    # 由後依序處理參數
    else:
        input_interval = DEFAULT_INTEVAL
        scarp_args = {'id':update.effective_chat.id, 'boardname':context.args[0], 'prev':''}
        if len(context.args) >1:
            excludeList = context.args[2].split('/') if len(context.args)==3 else None
            scarp_args.update({'exclude':excludeList})

            int_or_parse = (lambda x: int(x) if x.isdigit() else pytimeparse.parse(x))
            input_interval = (lambda x:(x*60) if x is not None and x > DEFAULT_INTEVAL else DEFAULT_INTEVAL)(int_or_parse(context.args[1]))
            if input_interval == DEFAULT_INTEVAL:
                context.bot.send_message(chat_id=update.effective_chat.id, text="USE DEFAULT.")

        joblist.append(job.run_repeating(callback_post_check, interval=input_interval, first=0, context=scarp_args))
        logging.info(joblist_retrieve(update.effective_chat.id))
        context.bot.send_message(chat_id=update.effective_chat.id, text="Job set.")

# TODO:改掉單純 JobQueue.stop -> 挑選 job 來取消
# if list empty > remove item in dict?
def callback_job_cancel(update:Update, context: CallbackContext):
    job.stop()
    context.bot.send_message(chat_id=update.effective_chat.id, text="Job canceled.")
# TODO: list all job with index in front
def callback_show_status(update:Update, context: CallbackContext):
    current_job = job.jobs()[0]
    exclude_term = "無" if not 'exclude' in current_job.context else current_job.context['exclude']
    status_output = (f"指定看板：{current_job.context['boardname']} \n"
    f"檢查間隔：{int(current_job.interval/60)} （分鐘）\n"
    f"排除關鍵字：{'/'.join(exclude_term)}\n"
    f"最後抓取值：{current_job.context['prev']}\n")

    context.bot.send_message(chat_id=update.effective_chat.id, text= status_output)

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
cancel_handler = CommandHandler('cancel',callback_job_cancel)
dispatcher.add_handler(check_handler)
dispatcher.add_handler(cancel_handler)
dispatcher.add_handler(status_handler)

updater.start_polling()
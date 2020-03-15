from telegram.ext import Updater,CallbackContext
from telegram import Update
import configparser
import logging
import scraper
from telegram.ext import CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.DEBUG)


config = configparser.ConfigParser()
config.read('config.ini')

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

def callback_post_check(context: CallbackContext):
    scr_obj = scraper.getTopicList(context.job.context['boardname'])
    
    if scr_obj['status']: 
        prev_scr_link = context.job.context['prev']
        if prev_scr_link == scr_obj['content']:
            context.bot.send_message(chat_id=context.job.context['id'], text= '重複')
        else:
            context.job.context['prev']= scr_obj['content']
            context.bot.send_message(chat_id=context.job.context['id'], text= scr_obj['content'])
    else:
        context.job.schedule_removal()
        #TODO: 完善敘述
        context.bot.send_message(
            chat_id = context.job.context['id'], 
            text= ''.join([scr_obj['content'],"\ncheck input"]))

def callback_post_set(update:Update, context: CallbackContext):
    if len(context.args) != 0:
        job.run_repeating(callback_post_check, interval=5,first=0,
            context={'id':update.effective_chat.id,'boardname':context.args[0],'prev':''})
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text="check args.")

def callback_job_cancel(update:Update, context: CallbackContext):
    job.stop()
    context.bot.send_message(chat_id=update.effective_chat.id, text="Job canceled.")

#TODO: 檢查狀態
#TODO: 特定詞過濾

### Bot set-up ###

# replace token you got
updater = Updater(token=config['telegram-bot']['token'],use_context=True)

dispatcher = updater.dispatcher
job = updater.job_queue

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

#TODO: 時間 arg
check_handler = CommandHandler('check', callback_post_set)
cancel_handler = CommandHandler('cancel',callback_job_cancel)
dispatcher.add_handler(check_handler)
dispatcher.add_handler(cancel_handler)

updater.start_polling()
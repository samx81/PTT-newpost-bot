from telegram.ext import Updater,CallbackContext
from telegram import Update
import configparser
import logging
import scraper
from telegram.ext import CommandHandler, MessageHandler, Filters

config = configparser.ConfigParser()
config.read('config.ini')
updater = Updater(token=config['telegram-bot']['token'],use_context=True)
dispatcher = updater.dispatcher
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

job = updater.job_queue
#TODO: 手動取消
start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# echo_handler = MessageHandler(Filters.text, echo)
# dispatcher.add_handler(echo_handler)

# TODO: 記住重複項
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
    job_check = job.run_repeating(callback_post_check, interval=5,
    context={'id':update.message.chat_id,'boardname':context.args[0],'prev':''})

    context.bot.send_message(chat_id=update.effective_chat.id, text="Job set.")

#TODO: 時間 arg
check_handler = CommandHandler('check', callback_post_set)
dispatcher.add_handler(check_handler)
updater.start_polling()
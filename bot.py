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

DEFAULT_INTEVAL = 10

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

def callback_post_check(context: CallbackContext):
    scarp_args = context.job.context
    newly_scrap = scraper.getNewPost(scarp_args['boardname'])
    
    if newly_scrap['status']: 

        # 檢查最新貼文與上次是否相同
        if scarp_args['prev'] == newly_scrap['url']:
            return
            # context.bot.send_message(chat_id=context.job.context['id'], text= '重複')
        # 檢查排除關鍵字
        elif scarp_args['exclude']:
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

def callback_post_set(update:Update, context: CallbackContext):
    # 不正確的參數就排除
    if not context.args or len(context.args)>3:
        context.bot.send_message(chat_id=update.effective_chat.id, text="check args.")

    # 由後依序處理參數
    else:
        excludeList = context.args[2].split('/') if len(context.args)==3 else ''

        input_interval = context.args[1] if isinstance(context.args[1],int) else DEFAULT_INTEVAL
        if input_interval == DEFAULT_INTEVAL:
            context.bot.send_message(chat_id=update.effective_chat.id, text="USE DEFAULT.")

        scarp_args ={'id':update.effective_chat.id, 'boardname':context.args[0],'exclude':excludeList, 'prev':''}
        job.run_repeating(callback_post_check, interval=input_interval, first=0, context=scarp_args)
        context.bot.send_message(chat_id=update.effective_chat.id, text="Job set.")

def callback_job_cancel(update:Update, context: CallbackContext):
    job.stop()
    context.bot.send_message(chat_id=update.effective_chat.id, text="Job canceled.")

#TODO: 檢查JOB狀態

### Bot set-up ###

# replace token you got
updater = Updater(token=config['telegram-bot']['token'],use_context=True)

dispatcher = updater.dispatcher
job = updater.job_queue

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

check_handler = CommandHandler('check', callback_post_set)
cancel_handler = CommandHandler('cancel',callback_job_cancel)
dispatcher.add_handler(check_handler)
dispatcher.add_handler(cancel_handler)

updater.start_polling()
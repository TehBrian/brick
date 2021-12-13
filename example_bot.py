import brick

my_options = brick.Options()
my_options.ai21_token = "[ai21 token]"
my_options.bot_token = "[discord bot token]"
brick.set_options(my_options)

brick.run()

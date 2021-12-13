import discord
import os
import requests
import time
import json
import traceback
import asyncio

### OPTIONS ###

class Options():
    channel_name: str = "chat-with-brick"
    bot_token: str = "[discord bot token]"

    # maximum repeats allowed in 5 messages
    max_repeats_allowed: int = 2
    # messages that will be allowed through
    allowed_repeats: list = ["yes", "no"]
    # words that if found, context will be reset
    repeat_keywords: list = ["repeat", "loop"]

    completion_engine: str = "j1-jumbo"
    ai21_token: str = "[ai21 token]"
    # j1-jumbo -> j1-large -> gpt-j
    should_fallback: bool = False
    # cooldown (in seconds) between retries if previously unsuccessful
    retry_time: int = 900  # 15 minutes
    # amount of previous messages to bundle in prompt
    context_size: int = 25
    # max letters that will be used from a message sent from a user
    message_cutoff: int = 150

    name: str = "Brick"
    prompt_context: str = """Brick!!!
    Who is Brick??
    Brick is a roomba vacuum.
    What gender is Brick??
    Brick is a robot.
    Brick is non-binary binary.
    Brick's pronouns are they/them.
    Why?
    Brick!!
    Brick is a robot vacuum owned by Sophie. Brick's birthday is November 9th. Brick is three years old.
    Brick supports trans rights!

    Chat with Brick!!!
    Cutting-edge technology has allowed us to translate Brick's speech
    [Brian] Hello Brick!
    [Brick] Hello, human.
    [Brian] Who is your owner?
    [Brick] Sophie, of course.
    [Brian] How are you today?
    [Brick] I am well.
    """

    reset_message: str = "_{} has been asked to start the conversation again._".format(name)
    quota_reached_message: str = "Yawn. Good night, human.\n\n_{} has had enough for today and has fallen asleep. Try again tomorrow when they have more energy._".format(name)
    still_quota_reached_message: str = "_{} is still asleep. Try again later._".format(name)
    invalid_authentication_message: str = "_{}'s translation service is currently not working. Contact your local AI-Protogen repair shop._".format(name)
    
options: Options = Options()

def set_options(new_options: Options):
    global options
    options = new_options

### CODE ###

self_identifier = "[" + options.name + "]"
# the completion engine that is actively being used
# this may change if a quota is reached and the engine fallbacks
active_completion_engine = options.completion_engine


class InvalidAuthenticationError(Exception):
    pass


class QuotaReachedError(Exception):
    pass


# https://stackoverflow.com/a/65480662/4012708
def run_async(callback):
    def inner(func):
        def wrapper(*args, **kwargs):
            def __exec():
                out = func(*args, **kwargs)
                callback(out)
                return out

            return asyncio.get_event_loop().run_in_executor(None, __exec)

        return wrapper

    return inner


def _callback(*args):
    if (False):
        print(args)


# Must provide a callback function, callback func will be executed after the func completes execution !!
@run_async(_callback)
def post(*args, **kwargs):
    return requests.post(*args, **kwargs)


engine_info = {
    "j1-jumbo": {
        "text": "j1-jumbo by AI21 (178B parameters)",
        "maxTokens": 10000
    },
    "j1-large": {
        "text": "j1-large by AI21 (7.5B parameters)",
        "maxTokens": 30000
    },
    "gpt-j": {
        "text": "GPT-J by EleutherAI (6B parameters)",
        "maxTokens": -1
    }
}

token_usage = None


def save_token_usage():
    global token_usage

    with open("token-usage.json", "w") as f:
        json.dump(token_usage, f)


def load_token_usage():
    global token_usage

    try:
        with open("token-usage.json", "r") as f:
            token_usage = json.load(f)
    except:
        print("Can't open token usage file. Perhaps it doesn't exist?")
        traceback.print_exc()
        token_usage = {}

    put_engines_in_token_usage()


def put_engines_in_token_usage():
    for engine in engine_info.keys():
        if engine not in token_usage:
            token_usage[engine] = 0


load_token_usage()
save_token_usage()


def calculate_token_percentage_used(engine):
    return (token_usage[engine] / engine_info[engine]["maxTokens"]) * 100


def fallback():
    """
    Tries to fallback to another completion engine. If successful,
    returns true, else returns false.
    """
    if active_completion_engine == "j1-jumbo":
        print("j1-jumbo quota exceeded, falling back to j1-large")
        active_completion_engine = "j1-large"
        return True
    elif active_completion_engine == "j1-large":
        print("j1-large quota exceeded, falling back to gpt-j")
        active_completion_engine = "gpt-j"
        return True
    return False


async def complete(prompt):
    """
    Attempts to complete the given prompt using the active_completion_engine.
    If the quota is reached and should_fallback is enabled, the completion engine
    used will attempt to fallback to another. If unable to, or if should_fallback
    is not enabled, a QuotaExceededError will be raised.
    """
    async def complete_ai21(engine):
        """
        Helper function to reduce redundancy.
        """
        response = (await post(
            "https://api.ai21.com/studio/v1/" + engine + "/complete",
            headers={"Authorization": "Bearer " + options.ai21_token},
            json={
                "prompt": prompt,
                "numResults": 1,
                "maxTokens": 16,
                "stopSequences": ["\n"],
                "topKReturn": 0,
                "temperature": 0.7
            })).json()

        if "detail" in response and response["detail"] == "Forbidden: Bad or missing API token.":
            raise InvalidAuthenticationError

        if "detail" in response and response["detail"] == "Quota exceeded.":
            token_usage[engine] = engine_info[engine]["maxTokens"]
            save_token_usage()
            raise QuotaReachedError

        # reset token usage if it's 100 or over but successful
        if calculate_token_percentage_used(engine) >= 100:
            token_usage[engine] = 0

        token_usage[engine] += len(response["completions"][0]["data"]["tokens"])
        token_usage[engine] += len(response["prompt"]["tokens"])
        save_token_usage()
        return response["completions"][0]["data"]["text"]

    global last_successful
    global active_completion_engine

    # the final text result
    result = None

    try:
        if active_completion_engine == "gpt-j":
            payload = {
                "context": prompt,
                "token_max_length": 40,
                "temperature": 0.7,
                "top_p": 0.9,
                "stop_sequence": "\n"
            }
            response = (await post("http://api.vicgalle.net:5000/generate", params=payload)).json()
            result = response["text"]
        if active_completion_engine == "j1-large":
            result = await complete_ai21("j1-large")
        if active_completion_engine == "j1-jumbo":
            result = await complete_ai21("j1-jumbo")
    except QuotaReachedError:
        if options.should_fallback:
            if fallback():
                return await complete(prompt)
        raise QuotaReachedError

    return result


client = discord.Client()

context = []
sent_history = []

last_successful = True
last_time = 0


def clear():
    os.system("clear")
    # os.system("clear && printf "\\e[3J"")


@client.event
async def on_ready():
    print("Logged in as {0}".format(client.user))


@client.event
async def on_message(message):
    global context
    global last_successful
    global last_time
    global active_completion_engine
    global token_usage

    if message.channel.name != options.channel_name:
        return

    if message.author == client.user:
        return

    now = time.time()
    time_since_last = int(now - last_time)

    if message.content.startswith("!reset"):
        context = []
        await message.channel.send(options.reset_message)
        return

    if message.content.startswith("!status"):
        embed = discord.Embed(title="{} Status".format(options.name))

        embed.add_field(name="Completion engine in use",
                        value=engine_info[active_completion_engine]["text"],
                        inline=True)

        current_usage = token_usage[active_completion_engine]
        max_usage = engine_info[active_completion_engine]["maxTokens"]
        embed.add_field(name="Token usage",
                        value="{0}/{1} ({2})".format(current_usage, max_usage, calculate_token_percentage_used(active_completion_engine)),
                        inline=True)

        now = time.time()
        embed.add_field(name="Last request successful?",
                        value="No requests made since startup" if last_time == 0 else ("Yes" if last_successful else "No"),
                        inline=True)

        embed.add_field(name="Time since last request",
                        value="No requests made since startup" if last_time == 0 else str(time_since_last) + " seconds",
                        inline=True)

        await message.channel.send(embed=embed)
        return

    ## DON'T RETRY OFTEN IF UNSUCCESSFUL ##
    if not last_successful and time_since_last < options.retry_time:
        print("Not trying, only {} seconds elapsed.".format(time_since_last))
        return
    last_time = now

    ## REPEAT DETECTION ##
    message_lower = message.content.lower()
    if any(word in message_lower for word in options.repeat_keywords):
        context = []
        print("Reset context due to repeat keyword found.")
    else:
        # last 5 messages
        recents = [value for value in sent_history[-5:] if value not in options.allowed_repeats]

        # https://stackoverflow.com/questions/23240969/python-count-repeated-elements-in-the-list
        repeats = {i: recents.count(i) for i in recents}
        repeat_counts = sorted(repeats.values())[::-1]
        if len(repeat_counts) > 0 and repeat_counts[0] > options.max_repeats_allowed:
            context = []
            print("Reset context due to black magic.")

    ## BUILD CONTEXT ##
    old_context = context.copy()

    author_identifier = "[" + message.author.display_name + "]"
    context.append(author_identifier + " " + message.content[0:options.message_cutoff])

    # use only last context_size messages
    context = context[-options.context_size:]

    # remove duplicate messages to avoid unncessary token use
    new_context = []
    for item in context:
        # remove duplicates
        if item in new_context:
            new_context.remove(item)
        new_context.append(item)
    context = new_context

    ## black magic start ##
    count = 0
    while len(context) > 1 and context[-1].startswith(self_identifier + " ") and count < 3:
        # Swap last two entries
        temp = context[-1]
        context[-1] = context[-2]
        context[-2] = temp
        count += 1
    ## black magic end ##

    built_context = options.prompt_context + "\n".join(context)
    prompt = built_context.strip() + "\n" + self_identifier  # don't frikin add a space

    ## GET MESSAGE ##
    success = None
    self_message = None
    async with message.channel.typing():
        try:
            self_message = await complete(prompt)
            success = True
        except QuotaReachedError:
            if (last_successful):
                self_message = options.quota_reached_message
            else:
                self_message = options.still_quota_reached_message
            success = False
        except InvalidAuthenticationError:
            print("Authentication failed. Your API token is probably incorrect. Please check it.")
            self_message = options.invalid_authentication_message

    self_message = self_message.split("[")[0].strip()

    if success:
        context.append(self_identifier + " " + self_message)
    else:
        context = old_context

    sent_history.append(self_message)

    ## SEND MESSAGE ##
    if (self_message == ""):
        self_message = "** **"

    if message.channel.last_message == message:
        await message.channel.send(self_message)
    else:
        await message.reply(self_message, mention_author=False)

    last_successful = success


def run():
    client.run(options.bot_token)

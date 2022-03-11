from discord.ext import commands

from .errors import MustBeSameChannel, NotConnectedToVoice, PlayerNotConnected


def voice_connected():
    def predicate(ctx: commands.Context):
        if not ctx.author.voice:
            raise NotConnectedToVoice("你不在語音0.0")

        return True

    return commands.check(predicate)


def player_connected():
    def predicate(ctx: commands.Context):
        if not ctx.voice_client:
            raise PlayerNotConnected("我不在語音裡 讓我加入試試？")

        return True

    return commands.check(predicate)


def in_same_channel():
    def predicate(ctx: commands.Context):
        if not ctx.voice_client:
            raise PlayerNotConnected("我不在語音裡 讓我加入試試？")

        if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            raise MustBeSameChannel("你跟偶不在同個頻率上 嘖嘖")

        return True

    return commands.check(predicate)


def voice_channel_player():
    def predicate(ctx: commands.Context):
        if not ctx.author.voice:
            raise NotConnectedToVoice("你不在語音0.0")

        if not ctx.voice_client:
            raise PlayerNotConnected("我不在語音裡 讓我加入試試？")

        if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            raise MustBeSameChannel("你跟偶不在同個頻率上 嘖嘖")

        return True

    return commands.check(predicate)

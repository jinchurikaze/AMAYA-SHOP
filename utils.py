import math


def js_num(n) -> str:
    """Format a number the way a JS template literal does (5.0 -> '5')."""
    if isinstance(n, bool):
        return str(n)
    if isinstance(n, int):
        return str(n)
    if math.isnan(n):
        return "NaN"
    if math.isinf(n):
        return "Infinity" if n > 0 else "-Infinity"
    if n == 0:
        return "0"
    if n == int(n) and abs(n) < 1e21:
        return str(int(n))
    return repr(n)


def can_moderate(guild, member, needed_perm: str) -> bool:
    """discord.py has no .bannable/.kickable, so work it out by hand."""
    me = guild.me
    if me is None or not getattr(me.guild_permissions, needed_perm):
        return False
    if member.id in (guild.owner_id, me.id):
        return False
    return me.top_role > member.top_role

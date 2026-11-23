import logging


# MT5 exposes filling_mode as a bitmask. These flags differ from ORDER_FILLING_*.
SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2


def immediate_filling_modes(mt5, info):
    accepts_both_fills = info.trade_exemode in (
        mt5.SYMBOL_TRADE_EXECUTION_REQUEST,
        mt5.SYMBOL_TRADE_EXECUTION_INSTANT,
    )
    immediate_modes = (
        (SYMBOL_FILLING_IOC, mt5.ORDER_FILLING_IOC),
        (SYMBOL_FILLING_FOK, mt5.ORDER_FILLING_FOK),
    )
    return [mode for flag, mode in immediate_modes if accepts_both_fills or info.filling_mode & flag]


def send_with_filling_modes(mt5, request, filling_modes):
    result = None
    for mode in filling_modes:
        result = mt5.order_send({**request, "type_filling": mode})
        # An explicit invalid-fill rejection is safe to retry immediately.
        if result is None or result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
            break
    return result


def _bot_positions(mt5, symbol, magic):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        logging.error("Could not read positions for %s: %s", symbol, mt5.last_error())
        return None
    if not positions:
        return ()

    account = mt5.account_info()
    if account is None:
        logging.error("Could not read the MT5 account type: %s", mt5.last_error())
        return None
    if account.margin_mode == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING:
        return [position for position in positions if position.magic == magic]

    # A netting position can combine bot and manual deals under one ticket.
    if len(positions) != 1:
        logging.error("Expected one netting position for %s, found %s.", symbol, len(positions))
        return None
    position, = positions
    deals = mt5.history_deals_get(position=position.identifier)
    trade_magics = {
        deal.magic for deal in deals or () if deal.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
    }
    if not trade_magics:
        logging.error("Could not verify ownership of netting position %s.", position.ticket)
        return None
    if magic not in trade_magics:
        return ()
    if trade_magics != {magic}:
        logging.error(
            "Netting position %s contains deals from multiple sources and needs manual review.",
            position.ticket,
        )
        return None
    return positions


def close_bot_positions(mt5, symbol, magic):
    """Attempt to flatten the bot's positions and confirm that none remain."""
    positions = _bot_positions(mt5, symbol, magic)
    if positions is None:
        return False
    if not positions:
        return True

    info = mt5.symbol_info(symbol)
    if info is None:
        logging.error("Could not read trading settings for %s: %s", symbol, mt5.last_error())
        return False
    execution = info.trade_exemode
    filling_modes = immediate_filling_modes(mt5, info)
    if not filling_modes:
        logging.error("No immediate filling mode available to close %s.", symbol)
        return False

    # Oldest first also supports brokers with FIFO closing rules.
    for position in sorted(positions, key=lambda position: (position.time_msc, position.ticket)):
        close_buy = position.type == mt5.POSITION_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_BUY if close_buy else mt5.ORDER_TYPE_SELL,
            "position": position.ticket,
            "deviation": 20,
            "magic": magic,
            "comment": "Economic release close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if execution != mt5.SYMBOL_TRADE_EXECUTION_MARKET:
            tick = mt5.symbol_info_tick(symbol)
            price = (tick.ask if close_buy else tick.bid) if tick else 0
            if price <= 0:
                logging.error("No closing quote for position %s.", position.ticket)
                continue
            request["price"] = price

        result = send_with_filling_modes(mt5, request, filling_modes)
        if result is None:
            logging.error("Close request for position %s failed: %s", position.ticket, mt5.last_error())
        elif result.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info("MT5 executed the close request for position %s.", position.ticket)
        else:
            logging.warning("Close result for position %s: %s - %s", position.ticket, result.retcode, result.comment)

    remaining = _bot_positions(mt5, symbol, magic)
    return remaining is not None and not remaining

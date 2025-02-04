from synthetix import *
from APICaller.Synthetix.SynthetixUtils import *
from TxExecution.Synthetix.SynthetixPositionControllerUtils import *
from GlobalUtils.globalUtils import *
from GlobalUtils.logger import *
from GlobalUtils.marketDirectory import MarketDirectory
import time

class SynthetixPositionController:
    def __init__(self):
        self.client = get_synthetix_client()
        self.leverage_factor = float(os.getenv('TRADE_LEVERAGE'))

    #######################
    ### WRITE FUNCTIONS ###
    #######################

    def execute_trade(self, opportunity, is_long: bool, trade_size: float):
        try:
            if not self.is_already_position_open():
                adjusted_trade_size = self.calculate_adjusted_trade_size(opportunity, is_long, trade_size)
                response = self.client.perps.commit_order(adjusted_trade_size, market_name=opportunity['symbol'], submit=True)
                if is_transaction_hash(response):
                    time.sleep(15)
                    position_data = self.handle_position_opened(opportunity)
                    logger.info("SynthetixPositionController - Order executed successfully")
                    return position_data
                else:
                    logger.error('SynthetixPositionController - Failed to execute order')
                    return None
            else:
                logger.error("SynthetixPositionController - execute_trade called while position already open")
        except Exception as e:
            logger.error(f"SynthetixPositionController - An error occurred while executing a trade: {e}")

    def close_all_positions(self):
        close_results = []
        try:
            for market in MarketDirectory:
                symbol = market.value['symbol']
                try:
                    close_details = self.close_position(market.value['market_id'])
                    if close_details:
                        close_results.append(close_details)
                except Exception as e:
                    logger.error(f"SynthetixPositionController - Error closing position for market {symbol}: {e}")
        except Exception as e:
            logger.error(f"SynthetixPositionController - General error in close all positions: {e}")
        
        return close_results if close_results else None


    def close_position(self, market_id: int):
        max_retries = 2 
        retry_delay_in_seconds = 3  
        
        for attempt in range(max_retries):
            try:
                position = self.client.perps.get_open_position(market_id=market_id)
                if position and position['position_size'] != 0:
                    close_position_details = {
                        'exchange': 'Synthetix',
                        'pnl': position['pnl'],
                        'accrued_funding': position['accrued_funding']
                    }

                    size = position['position_size']
                    inverse_size = size * -1
                    response = self.client.perps.commit_order(size=inverse_size, market_id=market_id, submit=True)

                    if is_transaction_hash(response):
                        logger.info(f'SynthetixPositionController - Position successfully closed: {close_position_details}')
                        return close_position_details
                    else:
                        logger.error('SynthetixPositionController - Failed to close position. Please check manually.')
                        raise Exception('SynthetixPositionController - Commit order failed, no transaction hash returned.')

            except Exception as e:
                logger.error(f"SynthetixPositionController - An error occurred while trying to close a position: {e}")
                if attempt < max_retries - 1:
                    logger.info("SynthetixPositionController - Attempting to retry closing position after delay...")
                    time.sleep(retry_delay_in_seconds)
                else:
                    raise e

    def approve_and_deposit_collateral(self, amount: int):
        try:
            self._approve_collateral_for_spot_market_proxy(amount)
            time.sleep(1)
            self._wrap_collateral(amount)
            time.sleep(1)
            self._approve_collateral_for_spot_market_proxy(amount)
            time.sleep(1)
            self._execute_atomic_order(amount, 'sell')
            time.sleep(1)
            self._approve_collateral_for_perps_market_proxy(amount)
            time.sleep(1)
            self._add_collateral(amount)
        except Exception as e:
            logger.error(f"SynthetixPositionController - An error occurred while attempting to add collateral: {e}")

    def _add_collateral(self, amount: int):
        try:
            tx = self.client.perps.modify_collateral(
                amount=amount, 
                market_id=0, 
                submit=True
            )
            if is_transaction_hash(tx):
                logger.info(f"SynthetixPositionController - Successfully added {amount} to collateral, market_id=0.")
        except Exception as e:
            logger.error(f"SynthetixPositionController - An error occurred while attempting to add collateral: {e}")

    def _create_account(self):
        try:
            account = self.client.perps.create_account(submit=True)
            logger.info(f"SynthetixPositionController - Account creation successful: {account}")
        except Exception as e:
            logger.error(f"SynthetixPositionController - Account creation failed. Error: {e}")

    def _approve_collateral_for_spot_market_proxy(self, amount: int):
        try:
            spot_market_proxy_address = self.client.spot.market_proxy.address
            approve_tx = self.client.spot.approve(
                target_address=spot_market_proxy_address, 
                market_id=0,
                amount=amount,
                submit=True
            )
            if is_transaction_hash(approve_tx):
                logger.info(f"SynthetixPositionController - Spot market collateral approval transaction successful. Transaction ID: {approve_tx}")
        except Exception as e:
            logger.error(f"SynthetixPositionController - Collateral approval for spot market failed. Error: {e}")

    def _approve_collateral_for_perps_market_proxy(self, amount: int):
        try:
            perps_market_proxy_address = self.client.perps.market_proxy.address
            approve_tx = self.client.spot.approve(
                target_address=perps_market_proxy_address, 
                market_id=0,
                amount=amount,
                submit=True
            )
            if is_transaction_hash(approve_tx):
                logger.info(f"SynthetixPositionController - Perps market collateral approval transaction successful. Transaction ID: {approve_tx}")
        except Exception as e:
            logger.error(f"SynthetixPositionController - Collateral approval for perps market failed. Error: {e}")

    def _wrap_collateral(self, amount: int):
        wrap_tx = self.client.spot.wrap(amount, market_name="sUSDC", submit=True)
        if is_transaction_hash(wrap_tx):
            logger.info(f"SynthetixPositionController - Wrap tx executed successfully")

    def _execute_atomic_order(self, amount: int, side: str):
        order_tx = self.client.spot.atomic_order(side, amount, market_name="sUSDC", submit=True)
        if is_transaction_hash(order_tx):
            logger.info(f"SynthetixPositionController - Atomic order transaction successful. Side: {side}, Transaction ID: {order_tx}")



    ######################
    ### READ FUNCTIONS ###
    ######################

    def handle_position_opened(self, opportunity):
        try:
            position = self.client.perps.get_open_position(market_name=opportunity['symbol'])
            position['symbol'] = opportunity['symbol']
            margin_details = self.client.perps.get_margin_info()
            position_details = {
                'position': position,
                'margin_details': margin_details
            }
            trade_data = parse_trade_data_from_position_details(position_details)
            return trade_data
        except Exception as e:
            logger.error(f"SynthetixPositionController - Failed to retrieve position data upon opening. Error: {e}")
            return None

    def get_available_collateral(self):
        try:
            account = self.get_default_account()
            balances = self.client.perps.get_collateral_balances(account)
            collateral = balances['sUSD']
            logger.info(f"SynthetixPositionController - Collateral balance called successfully: {collateral}")
            return collateral
        except Exception as e:
            logger.error(f"SynthetixPositionController - Failed to get available collateral. Error: {e}")
            return None

    def get_default_account(self):
        try:
            default_account = self.check_for_accounts()
            if default_account:
                default_account = default_account[0]
                logger.info("SynthetixPositionController - Successfully retrieved default account.")
                return default_account
            else:
                logger.error("SynthetixPositionController - No accounts found.")
                return None
        except Exception as e:
            logger.error(f"SynthetixPositionController - Failed to get the default account. Error: {e}")
            return None

    def check_for_accounts(self):
        try:
            account_ids = self.client.perps.account_ids
            if not account_ids:
                logger.info("SynthetixPositionController - No accounts found for wallet, creating new one.")
                self._create_account()
                return self.client.perps.account_ids
            else:
                logger.info(f"SynthetixPositionController - Accounts checked and found successfully: {account_ids}.")
                return account_ids
        except Exception as e:
            logger.error(f"SynthetixPositionController - Error checking for or creating accounts: {e}")
            return None
 
    def calculate_adjusted_trade_size(self, opportunity, is_long: bool, trade_size: float) -> float:
        try:
            trade_size_in_asset = get_asset_amount_for_given_dollar_amount(opportunity['symbol'], trade_size)
            trade_size_with_leverage = trade_size_in_asset * self.leverage_factor
            adjusted_trade_size_raw = adjust_trade_size_for_direction(trade_size_with_leverage, is_long)
            adjusted_trade_size = round(adjusted_trade_size_raw, 3)
            logger.info(f'SynthetixPositionController - levered trade size in asset calculated at {adjusted_trade_size}')
            return adjusted_trade_size
        except Exception as e:
            logger.error(f"SynthetixPositionController - Failed to calculate adjusted trade size. Error: {e}")
            return None

    def is_already_position_open(self) -> bool:
        try:
            positions = self.client.perps.get_open_positions()
            if not positions: 
                return False
            for key, position in positions.items():
                if float(position['position_size']) != 0:
                    return True
            return False
        except Exception as e:
            logger.error(f"SynthetixPositionController - Error while checking if position is open: {e}")
            return False

    def calculate_premium(self, symbol: str, size: float) -> float:
        try:
            market_id = MarketDirectory.get_market_id(symbol)
            quote_dict = self.client.perps.get_quote(size=size, market_id=market_id)
            index_price = float(quote_dict['index_price'])
            fill_price = float(quote_dict['fill_price'])
            
            if fill_price == 0:
                logger.error(f"SynthetixPositionController - Zero fill price error for symbol {symbol} with market ID {market_id}")
                return None
            
            premium = (fill_price - index_price) / index_price
            return premium

        except Exception as e:
            logger.error(f"SynthetixPositionController - Error calculating premium for symbol {symbol}: {e}")
            return None

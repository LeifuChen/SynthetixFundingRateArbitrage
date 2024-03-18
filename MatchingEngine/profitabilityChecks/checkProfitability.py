import sys
sys.path.append('/Users/jfeasby/SynthetixFundingRateArbitrage')

from GlobalUtils.globalUtils import *
from GlobalUtils.logger import logger
from TxExecution.Master.MasterPositionController import MasterPositionController

class ProfitabilityChecker:
    exchange_fees = {
        "Binance": 0.0004,  # 0.04% fee
        "ByBit": 0.00055,   # 0.055% fee
        "Synthetix": 0    # gas fees handled elsewhere
    }

    def __init__(self):
        self.position_controller = MasterPositionController()

    def get_capital_amount(self, opportunity) -> float:
        capital = self.position_controller.get_trade_size(opportunity)
        return capital

    def get_exchange_fee(self, exchange: str) -> float:
        return self.exchange_fees.get(exchange, 0)

    def calculate_position_cost(self, fee_rate: float, opportunity) -> float:
        capital = self.get_capital_amount()
        return capital * fee_rate

    def is_profitable(self, opportunity) -> bool:
        capital = self.position_controller.get_trade_size()
        long_capital = capital
        short_capital = capital

        long_fee_rate = self.get_exchange_fee(opportunity["long_exchange"])
        short_fee_rate = self.get_exchange_fee(opportunity["short_exchange"])

        long_cost = self.calculate_position_cost(long_capital, long_fee_rate)
        short_cost = self.calculate_position_cost(short_capital, short_fee_rate)

        daily_funding_profit = (long_capital * float(opportunity["long_funding_rate"]) +
                                short_capital * float(opportunity["short_funding_rate"]))
        total_cost = long_cost + short_cost

        return daily_funding_profit - total_cost > 0

    def minimum_profitable_duration(self, opportunity) -> float:
        capital = self.position_controller.get_trade_size(opportunity)
        long_capital = capital
        short_capital = capital

        long_fee_rate = self.get_exchange_fee(opportunity["long_exchange"])
        short_fee_rate = self.get_exchange_fee(opportunity["short_exchange"])

        long_cost = self.calculate_position_cost(long_capital, long_fee_rate)
        short_cost = self.calculate_position_cost(short_capital, short_fee_rate)

        daily_funding_profit = (long_capital * float(opportunity["long_funding_rate"]) +
                                short_capital * float(opportunity["short_funding_rate"]))

        total_initial_cost = long_cost + short_cost

        daily_net_profit = daily_funding_profit * 3 - total_initial_cost

        if daily_net_profit <= 0:
            return float('inf')

        days_to_profitability = total_initial_cost / daily_net_profit
        return days_to_profitability

    def calculate_profit(self, opportunity, period_hours: int):
        capital = self.position_controller.get_trade_size(opportunity)
        long_capital = capital
        short_capital = capital
        funding_rate_long = float(opportunity["long_funding_rate"])
        funding_rate_short = float(opportunity["short_funding_rate"])
        
        total_profit = (long_capital * funding_rate_long + short_capital * funding_rate_short) * (period_hours / 8)
        return total_profit * 5
    
    def find_most_profitable_opportunity(self, opportunities):
        max_profit = float('-inf')
        most_profitable = None
        for opportunity in opportunities:
            profit = self.calculate_profit(opportunity, 1)
            if profit > max_profit:
                max_profit = profit
                most_profitable = opportunity

        logger.info(f"best opportunity found, details: {most_profitable}")
        return most_profitable
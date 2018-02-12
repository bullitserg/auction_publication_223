from ets.ets_small_config_parser import ConfigParser as Parser
from inspect import getsourcefile
from os.path import dirname, normpath
from os import chdir

PATH = normpath(dirname(getsourcefile(lambda: 0)))
chdir(PATH)

CONFIG_FILE = 'auction_publisher.conf'


config = Parser(config_file=CONFIG_FILE)

out_dir = config.get_option('main', 'out_dir', string=True)
url_223_notifications = config.get_option('main', 'url_223_notifications', string=True)

log_file = config.get_option('main', 'log', string=True)


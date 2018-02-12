import re
import os
import requests
import tempfile
import argparse
import logger_module
from ets.ets_xml_worker import *
from os.path import join, exists, isdir, normpath
from lxml import etree
from config_parser import out_dir, url_223_notifications

PROGNAME = '223 Auctions publisher'
DESCRIPTION = '''Скрипт для публикации аукционов по 223-ФЗ'''
VERSION = '1.0'
AUTHOR = 'Belim S.'
RELEASE_DATE = '2018-02-09'


def show_version():
    print(PROGNAME, VERSION, '\n', DESCRIPTION, '\nAuthor:', AUTHOR, '\nRelease date:', RELEASE_DATE)


# обработчик параметров командной строки
def create_parser():
    parser = argparse.ArgumentParser(description=DESCRIPTION)

    parser.add_argument('-v', '--version', action='store_true',
                        help="Show version")

    parser.add_argument('-n', '--number', type=str,
                        help="Set auction number")

    parser.add_argument('-d', '--disable_publication', action='store_true',
                        help="Disabling publication after founding")

    parser.add_argument('-c', '--disable_confirming', action='store_true',
                        help="Disabling confirming of publication")
    return parser


def auction_publication_f(reg_number):

    def norm_and_join_path(*args):
        return normpath(join(*args))

    def get_url_part_from_onclick(onclick_link):
        onclick_link = re.sub('showPopup\(\'', '', onclick_link)
        return re.sub('\'\);return false;', '', onclick_link)

    if re.fullmatch(r'\d{11}', reg_number):
        print('Обработка извещения %s' % reg_number)
    else:
        print('Указан некорректный номер извещения')
        exit(1)

    payload = {'regNumber': reg_number}

    print('Ищем действующую версию извещения/проекта изменения процедуры %s' % reg_number)
    eis_223_notification_form_file = requests.get(EIS_URL + url_223_notifications,
                                                  params=payload,
                                                  headers=EIS_HEADERS)

    # создаем временный файл
    temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.html', delete=False).name

    with open(temp_file, mode='wb') as web_str:
        web_str.write(eis_223_notification_form_file.content)

    h_parser = etree.HTMLParser()
    tree = etree.parse(temp_file, h_parser)
    root = tree.getroot()  # xpath начинаем со следующего от root

    # находим номер версии и статус извещения
    notice_status = root.xpath(
        "body/div[3]/div/div/div[2]/div/div/div[2]/div[2]/div/div/div[1]/div/table/tbody/tr/td[3]")[0].text.strip()

    # если извещение актуально, то обрабатываем его
    if re.search('\(действующая\)', notice_status):
        print('Найдена действующая версия извещения')
        notice_print_form = root.xpath("body/div[3]/div/div/div[2]/div/div/div[2]/div[2]/div/div/div[1]/div/table/tbody/tr/td[2]/div/ul/li[1]")

        # получаем часть строки для скачивания принт-формы
        url_actual_version_xml_print_form_link_part = get_url_part_from_onclick(notice_print_form[0].attrib['onclick'])
        print('Ссылка на печатную форму:', EIS_URL + url_actual_version_xml_print_form_link_part)
    else:
        # если извещение неактуально
        # собираем словарь из всех версий проектов
        notice_projects = root.xpath("body/div[3]/div/div/div[2]/div/div/div[2]/div[2]/div/div/div[2]/div/table/tbody/tr/td[3]")
        notice_projects = map(lambda pr: pr.text.strip(), notice_projects)

        notice_projects_print_forms = root.xpath("body/div[3]/div/div/div[2]/div/div/div[2]/div[2]/div/div/div[2]/div/table/tbody/tr/td[2]/div/ul/li[1]")
        notice_projects_print_forms = map(lambda np: np.attrib['onclick'], notice_projects_print_forms)

        notice_projects_dict = dict(zip(notice_projects, notice_projects_print_forms))

        # находим нужный key, которому соответствует действующая версия
        for key in notice_projects_dict.keys():
            if re.search('\(действующая\)', key):
                print('Найдена действующая версия проекта изменения %s' % key[0])
                break
        else:
            'Не найдено актуальных версий!'
            exit(1)

        # получаем часть строки для скачивания принт-формы
        url_actual_version_xml_print_form_link_part = get_url_part_from_onclick(notice_projects_dict[key])
        print('Ссылка на печатную форму:', EIS_URL + url_actual_version_xml_print_form_link_part)

    # скачиваем страницу с принт-формой и записываем ее в файл
    eis_223_actual_version_xml_print_form_file = requests.get(EIS_URL + url_actual_version_xml_print_form_link_part,
                                                              headers=EIS_HEADERS)
    with open(temp_file, mode='wb') as web_str:
        web_str.write(eis_223_actual_version_xml_print_form_file.content)

    # получаем принт-форму
    tree = etree.parse(temp_file, h_parser)
    root = tree.getroot()  # xpath начинаем со следующего от root

    eis_223_actual_version_xml_print_form = root.xpath(".//*[@id='tabs-2']")[0].text.strip()

    # проверяем, что процедура для нашей площадки
    if not re.search(r'<url>www\.223\.etp-ets\.ru</url>', eis_223_actual_version_xml_print_form):
        print('Процедура опубликована не на www.223.etp-ets.ru\nВыход')
        exit(1)

    if not exists(out_dir):
        os.mkdir(out_dir)
    elif not isdir(out_dir):
        print('%s уже существует и это не директория' % out_dir)
        exit(1)

    # записываем печатную форму в файл с названием вида 31705120885.xml
    packet_name = reg_number + '.xml'
    packet = norm_and_join_path(out_dir, packet_name)

    with open(packet, mode='w', encoding='utf8') as xml_print_form_file:
        xml_print_form_file.write(eis_223_actual_version_xml_print_form)

    print('Расположение файла: ', packet)

    # Проверяем пакет на валидность
    valid_status, error = xml_check_valid(EIS_223_XSD_SCHEMA, packet)

    if valid_status:
        print(packet_name, 'валиден')
    else:
        print('Пакет не валиден: ', packet_name, error)

    # если указано не публиковать закупку, то заканчиваем
    if namespace.disable_publication:
        exit(0)

    # если не отключено ручное подтверждение, то выполняем необзодимые процедуры
    if not namespace.disable_confirming:
        do_publication = input('Опубликовать закупку? Y/n: ')

        # выходим, если пользователь отказался
        if not do_publication == 'Y':
            print('Выход без публикации пакета. Вы можете позже опубликовать его вручную')
            exit(0)

    # публикуем закупку
    print('Публикация закупки...')
    imported_packet, stdout, stderr = xml_import_223(packet)
    print('Info:', stdout)
    if stderr:
        print('Errors:', stderr)
        print('Пакет импортирован с именем %s (возможны ошибки)' % imported_packet)
    else:
        print('Пакет успешно импортирован с именем %s' % imported_packet)
    exit(0)


if __name__ == '__main__':
    logger = logger_module.logger()
    try:
        # парсим аргументы командной строки
        parser = create_parser()
        namespace = parser.parse_args()

        # вывод версии
        if namespace.version:
            show_version()
            exit(0)

        # публикация аукциона
        elif namespace.number:
            auction_publication_f(namespace.number)
            exit(0)

        else:
            show_version()
            print('For more information run use --help')
            exit(0)
    # если при исполнении будут исключения - кратко выводим на терминал, остальное - в лог
    except Exception as e:
        logger.fatal('Fatal error! Exit', exc_info=True)
        print('Critical error: %s' % e)
        print('More information in log file')
        exit(1)




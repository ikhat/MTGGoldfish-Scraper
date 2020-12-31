import re
import os
import json
import time
from datetime import datetime
from pprint import pprint

import requests
from bs4 import BeautifulSoup


TIME_DELAY = 0.1 # Time delay between server requests, in seconds.
LEGACY_TOURNAMENT_FILE = 'legacy_tournamentids.csv'
LEGACY_DECK_FILE = 'legacy_decks'


def soup_from_url(url: str) -> BeautifulSoup:
	'''
	'''
	page = requests.get(url)
	soup = BeautifulSoup(page.text, 'html.parser')
	return soup


def get_tournamentids_from_search_page(soup: BeautifulSoup):
	'''Gets a list of tournament ids from a page of search results.

	Args:
		soup (BeautifulSoup): BeautifulSoup object representing
			a page of search results from MTGGoldfish's advanced
			tournament search.

	Returns:
		A list of ids of tournaments on the page.
	'''
	link_table = soup.find('table', {'class':'table-striped'})

	if link_table is None:
		print('There are no tournaments listed on the page you entered.')
		return
	else:
		return (link.attrs['href'].rsplit('/')[-1] for link in link_table.find_all('a'))


def get_deckids_from_tournament(tournament):
	'''Gets list of MTGGoldfish deck IDs from an MTGGoldfish tournament page.

	Args:
		tournament (str): string representing a tournament page on MTGGoldfish.
			Can be either the integer tournament id, or the tournament url:
			e.g., https://www.mtggoldfish.com/tournament/scg-legacy-premier-iq-los-angeles#paper

	Returns:
		MTGGoldfish deck IDs for decks in the tournament, as a list of strings.
	'''
	if tournament.isdigit():
		url = 'https://www.mtggoldfish.com/tournament/' + tournament
	else:
		url = tournament

	soup = soup_from_url(url)
	deck_ids = (line.text for line in soup.find_all(class_='deck-slideshow-link'))

	return deck_ids


class mtgGoldfishSearch:
	'''Represents an Advanced Tournament Search on MTGGoldfish.com.

	Such a search would normally arise from here:
	https://www.mtggoldfish.com/tournament_searches/new

	Attributes:
		form (str): The tournament format being searched for.
		begin_date (str): The start date for the search.
		end_date (str): The end date for the search.
		keywords (str): Optional search keywords.
	'''

	BASE_URL = 'https://www.mtggoldfish.com/tournament_searches/create?utf8=%E2%9C%93&commit=Search'
	SEARCH_STRING =' &tournament_search%5Bname%5D={3}&tournament_search%5Bformat%5D={0}&tournament_search%5Bdate_range%5D={1}+-+{2}&page={4}'
	formats = ['standard', 'modern', 'pioneer', 'historic', 'pauper', 'legacy', 'vintage', 'penny dreadful']

	def __init__(self, fmt: str, begin_date: str, end_date: str, keywords: str = None):
		'''Initializes the mtgGoldfishSearch with all the search arguments.

		Args:
			form (str): The tournament format being searched for.
				Must be one of the formats that MTGGoldfish supports, as listed
				in the formats list.
			begin_date (str): The start date for the search.
			end_date (str): The end date for the search.
				Both dates expected in the format YYYY-MM-DD
			keywords (str): Optional search keywords.
				Only accepts strings with letters, numbers, and spaces.

		Raises:
			ValueError: In three cases:
				- If 'format' is not one of the supported formats,
				- If either of the dates aren't formatted as YYYY-MM-DD.
				- If 'keyword' is not alphanumeric (with spaces).
		'''
		if fmt.lower() not in self.formats:
			raise ValueError('Use one of the Magic: The Gathering formats supported by MTGoldfish.')
		else:
			self.fmt = fmt

		try:
			begin_date = datetime.strptime(begin_date, '%Y-%m-%d')
			end_date = datetime.strptime(end_date, '%Y-%m-%d')
		except ValueError:
			print('Error: Both date formats should be YYYY-MM-DD.')
			raise
		else:
			self.begin_date = begin_date
			self.end_date = end_date

		self.keywords = keywords
		if self.keywords is None: self.keywords = []
		elif self.keywords.replace(' ', '').isalnum() or self.keywords == '':
			self.keywords = self.keywords.split(' ')
		else:
			raise ValueError('Search keywords should be only alphanumeric (and spaces).')

	def get_tournaments(self):
		'''Gets the ids of all tournaments in the search results.'''
		for p in range(1, self.number_of_pages + 1):
		 	current_page = soup_from_url(self.url(p))
		 	yield from get_tournamentids_from_search_page(current_page)
		 	time.sleep(TIME_DELAY)

	def url(self, page_number: int = None) -> str:
		'''Returns the URL for the specified page of the search.

		Args:
			page_number: The page number in the results whose URL to get. Defaults to 1.
		'''
		if page_number == None:
			page_number = 1


		if not isinstance(page_number, int):
			raise TypeError('The page number must be an integer! You entered a {1}.'.format(self.number_of_pages, type(page_number)))
		elif page_number < 1 or page_number > self.number_of_pages:
			raise ValueError('The page number must be an integer between 1 and {0}! You entered {1}.'.format(self.number_of_pages, page_number))

		return self.page1_url[:-1] + str(page_number)

	@property
	def page1_url(self):
		'''Gets the URL for the first page of the search.'''
		if self.keywords:
			url_keywords = '+'.join([word for word in self.keywords])
		else:
			url_keywords = ''

		search_string = self.SEARCH_STRING.format(
			self.fmt,
			self.begin_date.strftime('%m%%2F%d%%2F%Y'),
			self.end_date.strftime('%m%%2F%d%%2F%Y'),
			url_keywords,
			'1'
			)

		return self.BASE_URL + search_string

	@property
	def page1_soup(self):
		'''Gets the BeautifulSoup object for the first page of search results'''
		return soup_from_url(self.page1_url)

	@property
	def number_of_pages(self):
		'''Gets the number of pages in search results.

		Finds the text content of the last page number button.
		'''
		pagination = self.page1_soup.find('ul', {'class':'pagination'})
		if pagination is None:
			return 1
		else:
			return int(pagination.find_all('a')[-2].text)


def get_deck_from_id(deckid: str) -> dict:
	'''Gets information about a deck from its MTGGoldfish deck ID.

	Args:
		deckid (str): Deck ID as a string, e.g., '435910'

	Returns:
		Dict with deck list and various metadata. e.g.,
		{
			'deck_id': '435911',
			'name': 'ad nauseam tendrils',
			'player': 'brandon osborne',
			'format': 'legacy',
			'tournament_id': '21494',
			'date': '2016-06-05',
			'event_name': 'scg legacy iq somerville',
			'standing': 2,
			'standing_type': 'rank',
			'maindeck' : [
				{
      				"cardName": "island",
      				"nCopies": 1
    			}, ...
			]
			'sideboard' : [
				{
      				"cardName": "carpet of flowers",
      				"nCopies": 1
    			}, ...
			]

		}
	'''
	def get_title(html_soup: BeautifulSoup) -> dict:
		'''Gets name and player of the deck.

		Extracts the words from an html element, for example:

		<h1 class='title'>
			Ad Nauseam Tendrils
			<span class='author'>by Brandon Osborne</span>
		</h1>

		Args:
			html_soup (BeautifulSoup): BeautifulSoup object created
				from a MTGGoldfish deck page.

		Returns:
			{
				'name' : deckName,
				'player' : deckPlayer
			}

			The page may not list a deck name, in which case
			deckName = None.
		'''
		title_data = [line for line in html_soup.find('h1', class_='title').text.split('\n') if line]
		deckPlayer = title_data[-1][3:].lower()
		if len(title_data) == 2:
			deckName = title_data[0].lower()
		else:
			deckName = None

		return { 'name' : deckName, 'player' : deckPlayer }


	def get_metadata(html_soup: BeautifulSoup) -> dict:
		'''Gets six pieces of metadata about the deck.

		Extracts the data from an html element, for example:

		<p class='deck-container-information'>
			Format: Legacy
			<br>
			Event: <a href="/tournament/21494">SCG Legacy IQ Somerville</a>, 2nd Place
			<br>
			Deck Date: Jun 5, 2016
		</p>

		Sometimes there are more lines in this element, so uses
		regular expressions to find the relevant lines.

		Args:
			html_soup (BeautifulSoup): BeautifulSoup object created
				from a MTGGoldfish deck page.

		Returns:
			{
				'format' : deckFormat,
				'tournament_id' : deckTournamentID,
				'date' : deckDate,
				'event' : deckEvent,
				'standing' : deckStanding,
				'standing_type' : standingType
			}

			All strings, except deckStanding which can be a string or integer,
			depending on what type of standings the tournament has.
		'''
		metadata_para = html_soup.find('p', class_='deck-container-information')
		deckTournamentID = metadata_para.a['href'].split('/')[-1]
		res = {
			'format' : 'Format: ([\w ]+)',
			'event'  : 'Event:\s+([\w\s\-#\/]+),*\s*\(*([\d\-]+)?',
			'date'   : 'Deck Date: ([\w, ]+)'
		}
		deckFormat = re.search(res['format'], metadata_para.text).group(1).lower()
		deckEvent, deckStanding = [match.lower() for match in re.search(res['event'], metadata_para.text).groups()]
		deckDate = str(datetime.strptime(re.search(res['date'], metadata_para.text).group(1), '%b %d, %Y').date())

		try:
			# Convert deckStanding to an integer if it's an integer.
			# If it is, the standings are rankings (1st, 2nd, etc.).
			# If it isn't, the standings are records (5-0, 3-2, etc.).
			deckStanding = int(deckStanding)
		except ValueError:
			standingType = 'record'
			pass
		else:
			standingType = 'rank'

		output = {
			'format' : deckFormat,
			'tournament_id' : deckTournamentID,
			'date' : deckDate,
			'event' : deckEvent,
			'standing' : deckStanding,
			'standing_type' : standingType
		}

		return output

	def get_price(html_soup: BeautifulSoup) -> dict:
		'''Gets the paper and Magic Online prices listed for the deck.

		Args:
			html_soup (BeautifulSoup): BeautifulSoup object created
				from a MTGGoldfish deck page.

		Returns:
			{ 'price' : priceDict },

			where priceDict is a dictionary of price data, e.g.:

			{
				'paper' : 2024,
				'online' : 387
			}

			Prices are in US Dollars and MTGO tix, respectively.
		'''
		raw_data = [price.previousSibling.strip() for price in html_soup.find_all('span', class_='cents')]
		paper_price = int(raw_data[0].split('\xa0')[1].replace(',',''))
		online_price = int(raw_data[1])

		priceDict = {
			'paper' : paper_price,
			'online' : online_price
		}

		return { 'price' : priceDict }

	def get_cards(html_soup: BeautifulSoup):
		list_raw = html_soup.find(id='deck_input_deck').attrs['value']
		decklist = [
			{
				'cardName' : line.split(' ', 1)[1].lower(),
				'nCopies' : int(line.split(' ', 1)[0])
			}
			if line != 'sideboard' else line for line in list_raw.split('\n')[:-1]]
		sideboard_index = decklist.index('sideboard')

		return { 'maindeck' : decklist[:sideboard_index], 'sideboard' : decklist[sideboard_index+1:] }

	soup = soup_from_url('https://www.mtggoldfish.com/deck/' + deckid)

	deck = { 'deck_id' : deckid	}
	deck.update(get_title(soup))
	deck.update(get_metadata(soup))
	deck.update(get_price(soup))
	deck.update(get_cards(soup))

	return deck


def update_legacy_tournament_list(from_scratch = False):
	'''Updates (or creates) a file listing legacy tournament ids.

	Args:
		from_scratch (bool): If True, the list of all tournaments is
			recompiled from scratch. If False, the list is updated with
			new tournaments.
	'''
	today = datetime.today().strftime('%Y-%m-%d')
	if from_scratch:
		search_from_scratch = mtgGoldfishSearch('legacy', '2011-01-01', today)
		all_legacy_tournaments = [int(tid) for tid in search_from_scratch.get_tournaments()]
		all_legacy_tournaments.sort()
		with open(LEGACY_TOURNAMENT_FILE, 'w', encoding='utf-8') as f:
			# Add them all to the file.
			# I don't understand what's happening with tournament id 10,
			# so I'm manually removing it here.
			f.write(','.join(str(tid) for tid in all_legacy_tournaments if tid != 10))
	else:
		with open(LEGACY_TOURNAMENT_FILE, 'r+', encoding='utf-8') as f:
			existing = [int(tid) for tid in f.read().split(',')]

		# Going back a few because sometimes they're a bit out of order.
		update_from = existing[-3]

		r = requests.get('https://www.mtggoldfish.com/tournament/' + str(update_from), stream=True)

		for line in r.iter_lines(decode_unicode=True):
			if 'Date:' in line:
				last_date = line[-10:]
				break

		update_search = mtgGoldfishSearch('legacy', last_date, today)
		tournaments_to_add = [int(tid) for tid in update_search.get_tournaments()]

		updated = list(set(existing + tournaments_to_add))
		updated.sort()

		with open(LEGACY_TOURNAMENT_FILE, 'w', encoding='utf-8') as f:
			f.write(','.join(str(tid) for tid in updated))


def get_all_legacy_decks(stop = None):
	'''Gets all Legacy decks for listed tournaments and writes them to
	file.

	Gets every tournament in LEGACY_TOURNAMENT_FILE, every deck in each
	tournament, and dumps them into LEGACY_DECKS_FILE. So far, just
	rebuilds the list from scratch each time. May add more
	functionality later.

	Args:
		stop: An optional argument to truncate how many tournaments
			are looked at, for quick tests.
	'''
	with open(LEGACY_TOURNAMENT_FILE, 'r', encoding='utf-8') as f:
		tournaments = [tid for tid in f.read().split(',')]

	if stop is None:
		stop = len(tournaments)

	with open('legacy_decks', 'w', encoding='utf-8') as f:
		for t in tournaments[:stop]:
			print('Looking at tournament {}!'.format(t))
			for d in get_deckids_from_tournament(t):
				deck = get_deck_from_id(d)
				json.dump(deck, f, ensure_ascii=False)
				f.write('\n')
				print('    Added deckid {0} from tournament {1} to file.'.format(d,t))
				time.sleep(TIME_DELAY)


if __name__ == '__main__':
	# Testing that everything works by looking at the first 10 tournaments.
	get_all_legacy_decks(10)

	# Adding some comments so this file shows up in a pull request.

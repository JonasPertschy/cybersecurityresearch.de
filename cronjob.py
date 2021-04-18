#Client
import requests
import json
import urllib.parse
import time
import os
from datetime import datetime
import hashlib
import pymsteams
from time import sleep
import random
import sqlite3
import subprocess
from git import Repo
import tweepy

#Twitter
auth = tweepy.OAuthHandler("...", "...")
auth.set_access_token("...", "...")
api = tweepy.API(auth)

#Microsoft Teams
connection = sqlite3.connect("cache.db")
webhook_EN = 'https://outlook.office.com/webhook/..'
webhook_DE = 'https://outlook.office.com/webhook/..'

#DeepL
deepl_auth_key = '...'

#Feedly
resource = "user/.../tag/global.annotated"
access_token = open("config/access_token", "r").read()


cursor = connection.cursor()

def translate_deepl(text_to_translate,language):
	url = 'https://api.deepl.com/v2/translate'
	payload = {'auth_key': deepl_auth_key,'text':text_to_translate,'target_lang':language,'source_lang':'EN'}
	r = requests.post(url, data=payload)
	translated_text = r.json()['translations'][0]['text']
	print('DEEPL-PRO:'+translated_text)
	return translated_text

def translate(text_to_translate,language):
	text_to_translate = text_to_translate.replace('\'','"')
	resp = cursor.execute("select count(*) from deepl where input='"+text_to_translate+"' and language = '"+language+"';")
	result = resp.fetchone()[0]
	if int(result) == 0:
		output = translate_deepl(text_to_translate,language).replace('\'','"')
		cursor.execute("INSERT INTO deepl VALUES('"+text_to_translate+"','"+language+"','"+output+"')")
		connection.commit()
		return output
	else:
		print("Served from cache")
		resp = cursor.execute("select output from deepl where input='"+text_to_translate+"' and language = '"+language+"' limit 1;")
		result = resp.fetchone()[0]
		return result

#Refreshing the access token
#POST /v3/auth/token
def token_refresh():
	refresh_token_file = open("config/refresh_token", "r")
	refresh_token = refresh_token_file.read()
	refresh_token_file.close()
	payload = {'refresh_token':refresh_token,'client_id':'feedlydev','client_secret':'feedlydev','grant_type':'refresh_token'}
	r = requests.post('https://cloud.feedly.com/v3/auth/token', data = payload)
	if r.status_code == requests.codes.ok:
		access_token_file = open("config/access_token", "w")
		access_token = r.json()['access_token']
		access_token_file.write(r.json()['access_token'])
		access_token_file.close()
	else:
		print("refresh_token_refresh_error")



def stream_api(resource,continuation=False,return_act=False,count=1000):
#Feed Contents CyberSecurity
#GET /v3/streams/:streamId/contents
#print('https://cloud.feedly.com/v3/streams/'+urllib.parse.quote_plus(resource)+'/contents'
	if continuation:
		print(continuation)
		appendix = "&continuation="+continuation
	elif os.path.isfile("config/"+resource+"/latest"):
		latest_file = open("config/"+resource+"/latest", "r")
		latest = latest_file.read()
		latest_file.close()
		appendix = "&newerThan="+latest
	elif not os.path.isdir("config/"+resource+"/"):
		os.makedirs("config/"+resource+"/")
		appendix  = ''
	else:
		appendix  = ''
	r = requests.get('https://cloud.feedly.com/v3/streams/'+urllib.parse.quote_plus(resource)+'/contents?count='+str(count)+appendix, headers={"Authorization": "Bearer "+access_token})
	if r.status_code == requests.codes.ok:
		json = r.json()
		#Write latest_file
		#print(r.json())
		if not continuation and "updated" in json:
			latest_file = open("config/"+resource+"/latest", "w+")
			latest = latest_file.write(str(json['updated']+1))
			latest_file.close()
		for item in json['items']:
			if "title" in item and len(item['annotations']):
				print(item["title"])
				if "canonicalUrl" in item:
					source = item['canonicalUrl']
				elif "canonical" in item:
					source = item['canonical'][0]['href']
				elif "alternate" in item:
					source = item['alternate'][0]['href']
				elif "htmlUrl" in item:
					source = item['htmlUrl']
				else:
					source = item['originId']
				md5 = hashlib.md5(source.encode('utf-8')).hexdigest()
				if not os.path.isfile("./hugo/content/post/"+md5+".md"):
					return_act = True
					myTeamsMessage = pymsteams.connectorcard(webhook_EN)
					myTeamsMessage.color("red")
					myMessageSection = pymsteams.cardsection()
					if(len(source.split("/"))>2):
						domain = source.split("/")[2].replace("www.","")
					else:
						domain = source
					if "author" in item:
						author = item['author']
					else:
						author = domain
					title = item['title'].replace('"','\'')
					myTeamsMessage.title(title)
					date =  datetime.utcfromtimestamp(int(str(item['published'])[:10])).strftime('%Y-%m-%dT%H:%M:%S-00:00')
					featured = "false"
					if "tags" in item:
						for tag in item['tags']:
						    if "TopStories" in tag['label']:
						        featured = "true"
					myTeamsMessage.addLinkButton(domain, source)
					markdown = ('+++\nauthor = "'+author+'"\ntitle = "'+title+'"\ndomain="'+domain+'"\ndate = "'+date+'"\nfeatured = '+featured+'\nSourcelink = "'+source+'"\ntags = [\n')
					if "keywords" in item:
						teams_keywords = ''
						for keyword in item['keywords']:
							if keyword.lower() not in ['security news','cybersecurity','hacking news','information security news','it information security','security','news','news industry','pierluigi paganini','security affairs']:
								print(keyword)
								markdown += '    "'+keyword+'",\n'
								teams_keywords += keyword+' '
						if len(teams_keywords) > 4:
							myMessageSection.addFact("Keywords", teams_keywords)
					if "visual" in item:
							if "edgeCacheUrl" in item['visual']:
								image_url = item['visual']['edgeCacheUrl']
							else:
								image_url = item['visual']['url']
							image_ending = item['visual']['url'].split(".")[-1]
							myMessageSection.addImage(image_url)
							if image_ending not in ["jpg","jpeg","png","gif"]:
								image_ending = "png"
							try:
								image_path = "/images/"+md5+"."+image_ending
								if not os.path.isfile("./hugo/static"+image_path):
									image_request = requests.get(image_url)
									image_file = open("./hugo/static"+image_path, "wb+")
									image_file.write(image_request.content)
									image_file.close()
								markdown +=']\nthumbnail = "'+image_path+'"\n+++\n'
							except:
								markdown +=']\n+++\n'
					else:
					        markdown +=']\n+++\n'
					teams_message_text = ''
					twitter_message = ''
					for annotation in item['annotations']:
						if "highlight" in annotation:
							markdown += annotation['highlight']['text']+'<br>\n'
							teams_message_text += annotation['highlight']['text']+' '
							twitter_message += annotation['highlight']['text']+' '
						else:
							markdown += annotation['comment']+'<br>\n'
							twitter_message += annotation['comment']+' '
					myTeamsMessage.text(teams_message_text)
					markdown += '<!--more-->'
					twitter_message = twitter_message.strip()
					twitter_message += " "+source
					twitter_message.replace("  ", " ")
					print('TWITTER',twitter_message)
					try:
						print(api.update_status(status=twitter_message))
					except:
						pass
					content_file = open("./hugo/content/post/"+md5+".md", "w+")
					content_file.write(markdown)
					content_file.close()
					myTeamsMessage.addSection(myMessageSection)
					try:
						myTeamsMessage.send()
					except:
						pass
				if not os.path.isfile("./hugo/content/post/"+md5+".de.md"):
					myTeamsMessage = pymsteams.connectorcard(webhook_DE)
					myTeamsMessage.color("red")
					myMessageSection = pymsteams.cardsection()
					if(len(source.split("/"))>2):
						domain = source.split("/")[2].replace("www.","")
					else:
						domain = source
					if "author" in item:
						author = item['author']
					else:
						author = domain
					myTeamsMessage.addLinkButton(domain, source)
					title = translate(item['title'],"DE")
					myTeamsMessage.title(title)
					date =  datetime.utcfromtimestamp(int(str(item['published'])[:10])).strftime('%Y-%m-%dT%H:%M:%S-00:00')
					featured = "false"
					if "tags" in item:
						for tag in item['tags']:
						    if "TopStories" in tag['label']:
						        featured = "true"
					markdown = ('+++\nauthor = "'+author+'"\ntitle = "'+title.replace("\"","")+'"\ndomain="'+domain+'"\ndate = "'+date+'"\nfeatured = '+featured+'\nSourcelink = "'+source+'"\ntags = [\n')
					if "visual" in item:
							if "edgeCacheUrl" in item['visual']:
								image_url = item['visual']['edgeCacheUrl']
							else:
								image_url = item['visual']['url']
							image_ending = item['visual']['url'].split(".")[-1]
							myMessageSection.addImage(image_url)
							if image_ending not in ["jpg","jpeg","png","gif"]:
								image_ending = "png"
							try:
								image_path = "/images/"+md5+"."+image_ending
								if not os.path.isfile("./hugo/static"+image_path):
									image_request = requests.get(image_url)
									image_file = open("./hugo/static"+image_path, "wb+")
									image_file.write(image_request.content)
									image_file.close()
								markdown +=']\nthumbnail = "'+image_path+'"\n+++\n'
							except:
								markdown +=']\n+++\n'
					else:
					        markdown +=']\n+++\n'
					teams_message_text = ''
					for annotation in item['annotations']:
						if "highlight" in annotation:
							text = translate(annotation['highlight']['text'],"DE")
							markdown += text+'<br>\n'
							teams_message_text += text+' '
						else:
							markdown += translate(annotation['comment'],"DE")+'<br>\n'
					myTeamsMessage.text(teams_message_text)
					markdown += '<!--more-->'

					content_file = open("./hugo/content/post/"+md5+".de.md", "w+")
					content_file.write(markdown)
					content_file.close()
					myTeamsMessage.addSection(myMessageSection)
					try:
						myTeamsMessage.send()
					except:
						pass
		if 'continuation' in json:
			print('continue')
			return stream_api(resource,json['continuation'],return_act)
		else:
			print('RETURN FUNCTION',return_act)
			return return_act
	else:
		if r.status_code == 401:
			token_refresh()
			print("Token refresh")
		print("Error status_code:",r.status_code)
		return False

def git_push():
	repo = Repo(r'./hugo/.git')
	repo.git.add('.')
	repo.index.commit('NEWS UPDATE')
	origin = repo.remote(name='origin')
	origin.push()
	print('Push to GIT!')


def hugo_compile():
	subproc =subprocess.Popen('hugo',cwd=r'./hugo/', shell=True, stdout=subprocess.PIPE)
	subproc.wait()
	return subproc.returncode



if stream_api(resource):
	if hugo_compile() == 0:
		print('Compile success')
		git_push()


connection.close()
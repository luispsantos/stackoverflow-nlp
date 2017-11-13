import pickle
from collections import defaultdict
import os
from global_variables import *
import json
import yaml
import random
import sys
import nltk
from tqdm import tqdm
import numpy as np

with open('config.yml', 'r') as f:
    config = yaml.load(f)

data_dir = config['dir_name']['data']
mappings_dir = config['dir_name']['mappings']

training_size = config['dataset_size']['training_set']
validation_size = config['dataset_size']['validation_set']
test_size = config['dataset_size']['test_set']

num_keep_tags = config['data_preprocess']['keep_tags']
num_keep_words = config['data_preprocess']['keep_words']
skip_top = config['data_preprocess']['skip_top']

min_word_freq = config['data_preprocess']['min_word_freq']
max_word_len = config['data_preprocess']['max_word_len']

save_word_mapping = config['data_preprocess']['save_word_mapping']
save_tag_mapping = config['data_preprocess']['save_tag_mapping']

with open(os.path.join(data_dir, in_file), 'rb') as f:
    data = pickle.load(f)

#before proceeding we must shuffle the data
#not doing so would mean our data was time dependent, that the test set would
#always be in the future compared to the training set, similar to a time series dataset
#while that scenario is indeed realistic it would further complicate our problem unnecessarily
random.seed(119)
random.shuffle(data)
num_posts = len(data)

tag_count = defaultdict(int)
num_tags = defaultdict(int)

word_count = defaultdict(int)
num_words = []

#iterate all posts of the training set
#and accumulate both word and tag frequency
print('Creating word and tag dictionaries for the training set')
for post_idx in tqdm(range(training_size)):

    post_body, tags = data[post_idx]

    #word frequency
    words = nltk.word_tokenize(post_body)
    num_words.append(len(words))
    for word in words:
        word_count[word] += 1

    #tag frequency
    num_tags[len(tags)] += 1

    for tag in tags:
        tag_count[tag] += 1


#we keep just the top tags(most frequent) in the training set
#and discard all other tags from the posts
sorted_tag_freq = sorted(tag_count, key=tag_count.get)[::-1]
keep_tags = sorted_tag_freq[:num_keep_tags]

tag_to_index = {tag:i for i, tag in enumerate(keep_tags)}
index_to_tag = {i:tag for i, tag in enumerate(keep_tags)}

print('Tag statistics')
print('Unique tags:', len(tag_count))
print('Number of tags per post:', ', '.join(['%s - %s' % (tag, count) for (tag, count) in sorted(num_tags.items())]))
print('Most common 10 tags:', ', '.join(sorted_tag_freq[:10]))

if save_tag_mapping:
    with open(os.path.join(mappings_dir, in_file[:-4] + '-tag-to-index.json'), 'w') as f:
        json.dump(tag_to_index, f, indent=2)

#simple word preprocess to reduce training set vocab size
word_count = {word:count for word, count in word_count.items() if count >= min_word_freq and len(word) < max_word_len}

#similar to tags, we keep just a portion of the words with most counts
#however for words the words with most counts are likely to be either
#punctuation or stop words, which depending on the task might not be
#so relevant and so we have an option to skip the top words as well
sorted_word_freq = sorted(word_count, key=word_count.get)[::-1]
keep_words = sorted_word_freq[skip_top:num_keep_words]

#add special tokens to word list
pad_idx = 0
start_idx = 1
oov_idx = 2
keep_words = ['_pad', '_start', '_oov'] + keep_words

word_to_index = {word:i for i, word in enumerate(keep_words)}
index_to_word = {i:word for i, word in enumerate(keep_words)}
training_set_words = set(sorted_word_freq)

num_words = np.asarray(num_words)
print('\nWord statistics')
print('Unique words:', len(word_count))
print('Number of words per post(post length): Avg - %0.1f, Std - %0.1f, Max - %d' %
      (num_words.mean(), num_words.std(), num_words.max()))

if save_word_mapping:
    with open(os.path.join(mappings_dir, in_file[:-4] + '-word-to-index.json'), 'w') as f:
        json.dump(word_to_index, f, indent=2)

#delete unnecessary variables with a big memory footprint
#del tag_count, sorted_tag_freq
#del word_count, sorted_word_freq



training_set = []
validation_set = []
test_set = []

not_done = True
seen_posts = 0

curr_mode = 'training'
usable_posts = 0
print('\nCreating training set')
pbar = tqdm(total=training_size)

while not_done:

    if seen_posts == num_posts:
        sys.exit("We have seen all posts but still couldn't fill up the training, validation or test sets, this is because too many 'non usable' posts got discarded. Try increasing the read_extra variable. Exiting ...")

    post_body, tags = data[seen_posts]
    seen_posts += 1

    #we convert the tags to indexes and keep just the top tags
    new_tags = [tag_to_index[tag] for tag in tags if tag in keep_tags]
    new_tags = tuple(new_tags)

    #if the resulting post has no tags, then it doesn't have value
    #for our purposes and so we discard it
    if len(new_tags) == 0:
        continue

    #we convert the words to indexes, if the word occured on the training set
    #but is not on keep_words we assign it oov, if the word didn't occur on the training
    #set we discard that word, this behavior is consistent with how keras handles NLP preprocessing
    words = nltk.word_tokenize(post_body)
    new_words = []
    for word in words:
        if word in keep_words:
            new_words.append(word_to_index[word])
        elif word in training_set_words:
            new_words.append(oov_idx)
        else:
            #ignore these words
            pass

    usable_posts += 1
    pbar.update(1)

    if curr_mode == 'training':
        training_set.append((new_words, new_tags))

        if usable_posts == training_size:
            curr_mode = 'validation'
            usable_posts = 0

            pbar.close()
            print('Creating validation set')
            pbar = tqdm(total=validation_size)

    elif curr_mode == 'validation':
        validation_set.append((new_words, new_tags))

        if usable_posts == validation_size:
            curr_mode = 'test'
            usable_posts = 0

            pbar.close()
            print('Creating test set')
            pbar = tqdm(total=test_size)

    elif curr_mode == 'test':
        test_set.append((new_words, new_tags))

        if usable_posts == test_size:
            #we're done now, we simply discard the remaining posts
            not_done = False
            pbar.close()

    else:
        sys.exit('This should not occur')



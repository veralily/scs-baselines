import ast
import pickle
import random
import itertools

import nltk
import torch
import progressbar
import pandas as pd

import src.data.config as cfg
import src.data.data as data


# Translate pandas dataframe cells
def gen_lit_eval(s):
    if isinstance(s, str):
        if ('["' in s or "['" in s) and ('"]' in s or "']" in s):
            new_s = ast.literal_eval(s)
        else:
            new_s = s
        if isinstance(new_s, str):
            return [nltk.casual_tokenize(s.lower())]
        else:
            return [nltk.casual_tokenize(i.lower()) for i in new_s]
    return []


def sent_lit_eval(s):
    if s:
        return nltk.casual_tokenize(s.lower())
    else:
        return []


def ctx_lit_eval(s):
    if isinstance(s, str):
        sents = s.split("|")
        return [nltk.casual_tokenize(i.lower()) for i in sents]
    return []


class NeuralGenModelDataLoader(data.DataLoader):
    def __init__(self, opt=None, batch_size=32):
        super(NeuralGenModelDataLoader, self).__init__(opt, batch_size)

        # Emotion/Motivations Generations
        self.ex = {}
        self.ex["pos"] = {}
        self.ex["neg"] = {}

        # Context sentences
        self.ctx = {}
        self.ctx["pos"] = {}
        self.ctx["neg"] = {}

        # Context Lengths
        self.ctx_lengths = {}
        self.ctx_lengths["pos"] = {}
        self.ctx_lengths["neg"] = {}

        # Sentences
        self.sent = {}
        self.sent["pos"] = {}
        self.sent["neg"] = {}

        # Sentence Lengths
        self.sent_lengths = {}
        self.sent_lengths["pos"] = {}
        self.sent_lengths["neg"] = {}

        # Unfilled and offset trackers
        self.unfilled = {}
        self.unfilled["neg"] = {}
        self.unfilled["pos"] = {}
        self.offset = {}
        self.offset["neg"] = {}
        self.offset["pos"] = {}

        # Remember ID of each entry
        self.ids = {}
        self.ids["pos"] = {}
        self.ids["neg"] = {}

        self.raw = {}
        self.raw_labels = {}

        self.ent = {}
        self.ent["pos"] = {}
        self.ent["neg"] = {}

        self.ent_labels = {}
        self.ent_labels["pos"] = {}
        self.ent_labels["neg"] = {}

        self.ent_init = {}
        self.ent_init["pos"] = {}
        self.ent_init["neg"] = {}

        self.sent_maxes = {}
        self.ctx_maxes = {}

        self.size = {}
        self.size["pos"] = {}
        self.size["neg"] = {}

    # Load data from file
    def load_data(self, opt, splits=["train"], type_="emotion",
                  exist=False, dl_type="neural", pruned=True):
        self.splits = splits
        self.type = type_

        if exist:
            w = "processed/{}/gen_{}_train-dev-test_data_loader.pth".format(
                self.type, dl_type)
            with open(w, "r") as f:
                self = torch.load(f)
                for split in self.splits:
                    self.offset["neg"][split] = \
                        {i: 0 for i in self.ex["neg"][split]}
                    self.unfilled["neg"][split] = \
                        set(self.offset["neg"][split].keys())
                    self.offset["pos"][split] = \
                        {i: 0 for i in self.ex["pos"][split]}
                    self.unfilled["pos"][split] = \
                        set(self.offset["pos"][split].keys())
                # print(self.offset)
            return self

        for split in splits:
            for pn in ["neg", "pos"]:
                self.ex[pn][split] = {}
                self.ctx[pn][split] = {}
                self.sent[pn][split] = {}
                self.ctx_lengths[pn][split] = {}
                self.sent_lengths[pn][split] = {}
                self.ids[pn][split] = {}
                self.ent[pn][split] = {}
                self.ent_labels[pn][split] = {}
                self.ent_init[pn][split] = {}
                self.size[pn][split] = {}
            self.raw[split] = {}
            self.raw_labels[split] = {}

            suffix = ""
            if split == "train":
                df_names = self.fnames[split]
            else:
                df_names = [self.fnames["{}_{}".format(split, type_)]]

            ents = pickle.load(open(
                self.fnames[split + "_entity" + suffix], "r"))
            num_ents = pickle.load(open(
                self.fnames[split + "_num_entities" + suffix], "r"))
            ent_ments = pickle.load(open(
                self.fnames[split + "_entity_mentions" + suffix], "r"))

            print("Reading from Data File")

            df = None
            for df_name in df_names:
                if df is None:
                    df = pd.read_csv(df_name)
                else:
                    df = pd.concat(
                        [df, pd.read_csv(df_name)], ignore_index=True)

            print("Done reading data")

            print("Getting maximum lengths")
            print("Done reading data")
            self.sent_maxes[split] = self.get_maxes(
                df["sentence"].apply(sent_lit_eval))
            self.ctx_maxes[split] = self.get_maxes(
                df["context"].apply(ctx_lit_eval), ctx=True)
            print("Got maximum lengths")

            print("Putting Data in Tensors")
            print("Doing {}".format(split))

            if split == "train":
                id_idx = "freerespworkerid"
            else:
                if self.type == "emotion":
                    id_idx = "emotionworkerid"
                else:
                    id_idx = "motiveworkerid"

            n_cond = ((df[self.type] == "['none']") |
                      (df[self.type] == '["none"]'))
            nones = df[n_cond]

            s_cond = ((df[self.type] != "['none']") &
                      (df[self.type] != '["none"]'))
            somes = df[s_cond]

            bar = progressbar.ProgressBar(max_value=len(nones.index))
            bar.update(0)

            print("DOING NEGATIVES")
            for i in nones.index:
                row = nones.loc[i]
                sid = row["storyid"]
                self.do_row(row, ents, ent_ments[sid],
                            num_ents[sid], split, "neg", id_idx)
                bar.update(bar.value + 1)

            print("DOING POSITIVES")
            bar = progressbar.ProgressBar(max_value=len(somes.index))
            bar.update(0)

            for i in somes.index:
                row = somes.loc[i]
                sid = row["storyid"]
                self.do_row(row, ents, ent_ments[sid], num_ents[sid],
                            split, "pos", id_idx, (pruned and
                            (type_ == "motivation")))
                bar.update(bar.value + 1)

            self.offset["neg"][split] = {i: 0 for i in self.ex["neg"][split]}
            self.unfilled["neg"][split] = set(self.offset["neg"][split].keys())
            self.offset["pos"][split] = {i: 0 for i in self.ex["pos"][split]}
            self.unfilled["pos"][split] = set(self.offset["pos"][split].keys())

        return self

    def do_context(self, ctx_, char_lines, line_num):
        # Get lines in story where character appears
        # To trim context to right parts
        ctx = []
        for line in char_lines:
            if line < line_num:
                ctx += [self.vocabs["sentence"][i] for i in ctx_[line - 1]]
        return ctx

    def do_row(self, row, ents, ent_ments, num_ents,
               split, pn, id_idx, pruned=False):

        gens = gen_lit_eval(row[self.type])

        raw_sent = sent_lit_eval(row["sentence"])
        sent = [self.vocabs["sentence"][i] for i in raw_sent]
        ctx_ = ctx_lit_eval(row["context"])

        # Find entity in entity file
        story = row["storyid"]
        char = row["char"]
        char_lines = ents[(story, char)]
        line_num = row["linenum"]

        # Get lines in story where character appears
        # To trim context to right parts
        ctx = self.do_context(ctx_, char_lines, line_num)

        sl = len(sent)
        cl = len(ctx)

        sent_diff = self.sent_maxes[split] - sl
        ctx_diff = self.ctx_maxes[split].get(line_num - 2, 1) - cl

        sent += [0] * sent_diff
        ctx += [0] * ctx_diff

        for gen_num, raw_gen in enumerate(gens):
            if raw_gen and raw_gen[0] == "to" and pruned:
                raw_gen = raw_gen[1:]
            if raw_gen and raw_gen[0] == "be" and pruned:
                raw_gen = raw_gen[1:]
            if raw_gen and raw_gen[-1] == ".":
                raw_gen = raw_gen[:-1]

            gen = [self.vocabs[self.type][i] for i in raw_gen]

            gen.append(self.vocabs[self.type]["<end>"])
            gen.insert(0, self.vocabs[self.type]["<start>"])

            key = (len(gen), row["linenum"])

            # Get story id_
            id_ = (story, char, line_num, row[id_idx], gen_num)

            if key not in self.sent[pn][split]:
                self.sent[pn][split][key] = \
                    torch.LongTensor(sent).unsqueeze(0)
                self.ctx[pn][split][key] = \
                    torch.LongTensor(ctx).unsqueeze(0)
                self.ex[pn][split][key] = \
                    torch.LongTensor(gen).unsqueeze(0)
                self.sent_lengths[pn][split][key] = \
                    torch.LongTensor([sl])
                self.ctx_lengths[pn][split][key] = \
                    torch.LongTensor([cl])
                self.ids[pn][split][key] = [id_]
            else:
                self.sent[pn][split][key] = torch.cat(
                    [self.sent[pn][split][key],
                     torch.LongTensor(sent).unsqueeze(0)], 0)
                self.ctx[pn][split][key] = torch.cat(
                    [self.ctx[pn][split][key],
                     torch.LongTensor(ctx).unsqueeze(0)], 0)
                self.ex[pn][split][key] = torch.cat(
                    [self.ex[pn][split][key],
                     torch.LongTensor(gen).unsqueeze(0)], 0)
                self.sent_lengths[pn][split][key] = torch.cat(
                    [self.sent_lengths[pn][split][key],
                     torch.LongTensor([sl])], 0)
                self.ctx_lengths[pn][split][key] = torch.cat(
                    [self.ctx_lengths[pn][split][key],
                     torch.LongTensor([cl])], 0)
                self.ids[pn][split][key] += [id_]
            self.raw[split][id_] = self.raw[split].get(id_, []) + [raw_sent]
            self.raw_labels[split][id_] = \
                self.raw_labels[split].get(id_, []) + [raw_gen]
            self.size[pn][split][key] = self.size[pn][split].get(key, 0) + 1

    def sample_keys(self, split, pn="pos"):
        return random.sample(self.unfilled[pn][split], 1)[0]

    def shuffle_sequences(self, split, pn, keys):
        orders = {}
        for key in keys:
            ex_order = torch.LongTensor(
                range(self.ex[pn][split][key].size(0)))
            if self.is_cuda:
                ex_order = ex_order.cuda()
            random.shuffle(ex_order)
            orders[key] = ex_order
            self.ex[pn][split][key] = \
                self.ex[pn][split][key].index_select(0, ex_order)
            self.sent[pn][split][key] = \
                self.sent[pn][split][key].index_select(0, ex_order)
            self.ctx[pn][split][key] = \
                self.ctx[pn][split][key].index_select(0, ex_order)
            self.sent_lengths[pn][split][key] = \
                self.sent_lengths[pn][split][key].index_select(0, ex_order)
            self.ctx_lengths[pn][split][key] = \
                self.ctx_lengths[pn][split][key].index_select(0, ex_order)
            self.ids[pn][split][key] = [self.ids[pn][split][key][i]
                                        for i in ex_order]
        return orders

    # keyss should be a list of keyss to reset
    def reset_offsets(self, split=None, pn=None, keyss=None, shuffle=False):
        def reset_offset(split, pn, keyss):
            for keys in keyss:
                if keys in self.offset[pn][split]:
                    self.offset[pn][split][keys] = 0
                else:
                    print("keys not in offset")
            self.unfilled[pn][split] = \
                self.unfilled[pn][split].union(keyss)

        if not split:
            splits = self.splits
        else:
            splits = [split]

        if not pn:
            types = ["pos", "neg"]
        else:
            types = [pn]

        orders = {}

        for split, pn in itertools.product(splits, types):
            orders.setdefault(pn, {})
            if not keyss:
                keyss = self.offset[pn][split].keys()
            if shuffle:
                orders[pn][split] = \
                    self.shuffle_sequences(split, pn, keyss)
            reset_offset(split, pn, keyss)
            print(split)
            print(pn)
            # print(self.offset[pn][split])
        return orders

    def sample_batches(self, split, pn, keys=None, bs=None):
        # If specific key isn't specified, sample a key
        if not keys:
            keys = self.sample_keys(split, pn)

        if not bs:
            bs = self.batch_size

        offset = self.offset[pn][split]

        # Choose sequences to batch
        start_idx = offset[keys]
        final_idx = offset[keys] + bs

        num_sentences = self.sent[pn][split][keys].size(0)
        examples = self.ex[pn][split][keys]
        sentence = self.sent[pn][split][keys]
        sentence_lengths = self.sent_lengths[pn][split][keys]
        context = self.ctx[pn][split][keys]
        context_lengths = self.ctx_lengths[pn][split][keys]
        ids = self.ids[pn][split][keys]

        # Check if final index is greater than number of sequences
        if final_idx < num_sentences:
            idx_range = range(start_idx, final_idx)
            idxs = torch.LongTensor(idx_range)
            # Update offset for next access of this key
            self.offset[pn][split][keys] += bs
        else:
            # If it is, take a subset of the self.batch_size
            idx_range = range(start_idx, num_sentences)
            idxs = torch.LongTensor(idx_range)
            self.offset[pn][split][keys] = 0
            if keys in self.unfilled[pn][split]:
                # This key has been visited completed
                self.unfilled[pn][split].remove(keys)

        if self.is_cuda:
            idxs = idxs.cuda(cfg.device)

        ss = sentence.index_select(0, idxs)
        sl = sentence_lengths.index_select(0, idxs)
        cs = context.index_select(0, idxs)
        cl = context_lengths.index_select(0, idxs)
        ex = examples.index_select(0, idxs)
        idss = ids[idx_range[0]:idx_range[-1] + 1]

        return ex, ss, sl, cs, cl, None, None, None, idss, keys

    def cuda(self, device_id=None):
        if device_id is None:
            device_id = cfg.device
        for pn in self.sent.keys():
            for split in self.sent[pn].keys():
                for key in self.sent[pn][split].keys():
                    self.sent[pn][split][key] = \
                        self.sent[pn][split][key].cuda(device_id)
                    self.sent_lengths[pn][split][key] = \
                        self.sent_lengths[pn][split][key].cuda(device_id)
                    self.ctx[pn][split][key] = \
                        self.ctx[pn][split][key].cuda(device_id)
                    self.ctx_lengths[pn][split][key] = \
                        self.ctx_lengths[pn][split][key].cuda(device_id)
                    self.ex[pn][split][key] = \
                        self.ex[pn][split][key].cuda(device_id)

        self.is_cuda = True


class MemoryGenModelDataLoader(NeuralGenModelDataLoader):
    def __init__(self, opt=None, batch_size=32):
        super(MemoryGenModelDataLoader, self).__init__(opt, batch_size)
        self.is_ren = True

    def do_context(self, ctx_, char_lines, line_num):
        ctx = {}
        for line in range(len(ctx_)):
            if line < line_num:
                ctx[line + 1] = [self.vocabs["sentence"][i]
                                 for i in ctx_[line]]
        return ctx

    # ent_ments is entities mentioned in every line
    # num_ents is the entity identity
    def do_entities(self, ent_ments, num_ents):
        elabel = {}
        eids = [0] * len(num_ents)

        # Get entity ids from vocab
        for ent, idx in num_ents.iteritems():
            if ent.lower() not in self.vocabs["entity"]._index:
                print(ent.lower())
            eids[idx] = self.vocabs["entity"][ent.lower()]

        # Get entity labels at each step for
        # additional supervision
        for i in range(1, 6):
            ent_list = ent_ments.get(i, [])
            elabel[i] = [0] * len(num_ents)
            for ent in ent_list:
                elabel[i][num_ents[ent]] = 1
        return eids, elabel

    def do_row(self, row, ents, ent_ments, num_ents,
               split, pn, id_idx, pruned=False):

        story = row["storyid"]
        char = row["char"]
        line_num = row["linenum"]

        gens = gen_lit_eval(row[self.type])

        raw_sent = sent_lit_eval(row["sentence"])
        ctx_ = ctx_lit_eval(row["context"])

        char_lines = ents[(story, char)]

        # Get lines in story where character appears
        # To trim context to right parts
        ctx = self.do_context(ctx_, char_lines, line_num)

        # Find entity in entity file
        eids, elabels = self.do_entities(ent_ments, num_ents)

        # Make sentence
        sent = [self.vocabs["sentence"][i] for i in raw_sent]
        sl = len(sent)
        sent_diff = self.sent_maxes[split] - sl
        sent += [0] * sent_diff

        # Make contexts
        clengths = {}
        for i in ctx:
            clengths[i] = len(ctx[i])
            ctx_diff = self.ctx_maxes[split][i - 1] - clengths[i]
            ctx[i] += [0] * ctx_diff

        for gen_num, raw_gen in enumerate(gens):
            if raw_gen and raw_gen[0] == "to" and pruned:
                raw_gen = raw_gen[1:]
            if raw_gen and raw_gen[0] == "be" and pruned:
                raw_gen = raw_gen[1:]
            if raw_gen and raw_gen[-1] == ".":
                raw_gen = raw_gen[:-1]

            gen = [self.vocabs[self.type][i] for i in raw_gen]

            gen.append(self.vocabs[self.type]["<end>"])
            gen.insert(0, self.vocabs[self.type]["<start>"])

            key = (len(gen), row["linenum"], len(num_ents))

            # Get story id_
            id_ = (story, char, line_num, row[id_idx], gen_num)

            if key not in self.sent[pn][split]:
                self.sent[pn][split][key] = \
                    torch.LongTensor(sent).unsqueeze(0)
                self.ex[pn][split][key] = \
                    torch.LongTensor(gen).unsqueeze(0)
                self.sent_lengths[pn][split][key] = \
                    torch.LongTensor([sl])
                self.ent[pn][split][key] = \
                    torch.LongTensor([num_ents[char]])
                self.ent_init[pn][split][key] = \
                    torch.LongTensor(eids).unsqueeze(0)
                self.ids[pn][split][key] = [id_]

                self.ctx[pn][split][key] = {}
                self.ctx_lengths[pn][split][key] = {}
                self.ent_labels[pn][split][key] = {}
                for i in range(1, key[1]):
                    self.ctx[pn][split][key][i] = \
                        torch.LongTensor(ctx[i]).unsqueeze(0)
                    self.ctx_lengths[pn][split][key][i] = \
                        torch.LongTensor([clengths[i]])
                    self.ent_labels[pn][split][key][i] = \
                        torch.FloatTensor([elabels[i]])
                self.ent_labels[pn][split][key][key[1]] = \
                    torch.FloatTensor([elabels[key[1]]])
            else:
                self.sent[pn][split][key] = torch.cat(
                    [self.sent[pn][split][key],
                     torch.LongTensor(sent).unsqueeze(0)], 0)
                self.ex[pn][split][key] = torch.cat(
                    [self.ex[pn][split][key],
                     torch.LongTensor(gen).unsqueeze(0)], 0)
                self.sent_lengths[pn][split][key] = torch.cat(
                    [self.sent_lengths[pn][split][key],
                     torch.LongTensor([sl])], 0)
                self.ent[pn][split][key] = torch.cat(
                    [self.ent[pn][split][key],
                     torch.LongTensor([num_ents[char]])], 0)
                self.ent_init[pn][split][key] = torch.cat(
                    [self.ent_init[pn][split][key],
                     torch.LongTensor(eids).unsqueeze(0)], 0)
                for i in range(1, key[1]):
                    # try:
                    self.ctx[pn][split][key][i] = torch.cat(
                        [self.ctx[pn][split][key][i],
                         torch.LongTensor(ctx[i]).unsqueeze(0)], 0)
                    self.ctx_lengths[pn][split][key][i] = torch.cat(
                        [self.ctx_lengths[pn][split][key][i],
                         torch.LongTensor([clengths[i]])], 0)
                    self.ent_labels[pn][split][key][i] = torch.cat(
                        [self.ent_labels[pn][split][key][i],
                         torch.FloatTensor([elabels[i]])], 0)
                self.ent_labels[pn][split][key][key[1]] = torch.cat(
                    [self.ent_labels[pn][split][key][key[1]],
                     torch.FloatTensor([elabels[key[1]]])], 0)
                self.ids[pn][split][key] += [id_]
            self.raw[split][id_] = self.raw[split].get(id_, []) + [raw_sent]
            self.raw_labels[split][id_] = \
                self.raw_labels[split].get(id_, []) + [raw_gen]
            self.size[pn][split][key] = self.size[pn][split].get(key, 0) + 1

    def sample_batches(self, split, pn, keys=None, bs=None):
        # If specific key isn't specified, sample a key
        if not keys:
            keys = self.sample_keys(split, pn)

        if not bs:
            bs = self.batch_size

        offset = self.offset[pn][split]

        # Choose sequences to batch
        start_idx = offset[keys]
        final_idx = offset[keys] + bs

        num_sentences = self.sent[pn][split][keys].size(0)
        examples = self.ex[pn][split][keys]
        sentence = self.sent[pn][split][keys]
        sentence_lengths = self.sent_lengths[pn][split][keys]
        context = self.ctx[pn][split][keys]
        context_lengths = self.ctx_lengths[pn][split][keys]
        ent = self.ent[pn][split][keys]
        ent_init = self.ent_init[pn][split][keys]
        ent_labels = self.ent_labels[pn][split][keys]
        ids = self.ids[pn][split][keys]

        # Check if final index is greater than number of sequences
        if final_idx < num_sentences:
            idx_range = range(start_idx, final_idx)
            idxs = torch.LongTensor(idx_range)
            # Update offset for next access of this key
            self.offset[pn][split][keys] += bs
        else:
            # If it is, take a subset of the self.batch_size
            idx_range = range(start_idx, num_sentences)
            idxs = torch.LongTensor(idx_range)
            self.offset[pn][split][keys] = 0
            if keys in self.unfilled[pn][split]:
                # This key has been visited completed
                self.unfilled[pn][split].remove(keys)

        if self.is_cuda:
            idxs = idxs.cuda(cfg.device)

        s = sorted(context.keys())

        ss = sentence.index_select(0, idxs)
        sl = sentence_lengths.index_select(0, idxs)
        cs = {cn: context[cn].index_select(0, idxs) for cn in s}
        cl = {cn: context_lengths[cn].index_select(0, idxs) for cn in s}
        e = ent.index_select(0, idxs)  # entity label
        ei = ent_init.index_select(0, idxs)  # entity identities for init state
        el = {cn: ent_labels[cn].index_select(0, idxs) for cn in s}
        el[keys[1]] = ent_labels[keys[1]].index_select(0, idxs)
        ex = examples.index_select(0, idxs)
        idss = ids[idx_range[0]:idx_range[-1] + 1]

        return ex, ss, sl, cs, cl, e, ei, el, idss, keys

    def cuda(self, device_id=None):
        self.is_cuda = True
        if device_id is None:
            device_id = cfg.device
        for pn in self.sent.keys():
            for split in self.sent[pn].keys():
                for key in self.sent[pn][split].keys():
                    self.sent[pn][split][key] = \
                        self.sent[pn][split][key].cuda(device_id)
                    self.sent_lengths[pn][split][key] = \
                        self.sent_lengths[pn][split][key].cuda(device_id)
                    self.ent[pn][split][key] = \
                        self.ent[pn][split][key].cuda(device_id)
                    self.ent_init[pn][split][key] = \
                        self.ent_init[pn][split][key].cuda(device_id)
                    for i in range(1, key[1]):
                        self.ctx[pn][split][key][i] = \
                            self.ctx[pn][split][key][i].cuda(device_id)
                        self.ctx_lengths[pn][split][key][i] = \
                            self.ctx_lengths[pn][split][key][i].cuda(device_id)
                        self.ent_labels[pn][split][key][i] = \
                            self.ent_labels[pn][split][key][i].cuda(device_id)
                    self.ent_labels[pn][split][key][key[1]] = \
                        self.ent_labels[pn][split][key][key[1]].cuda(device_id)
                    self.ex[pn][split][key] = \
                        self.ex[pn][split][key].cuda(device_id)

    def shuffle_sequences(self, split, pn, keys):
        orders = {}
        for key in keys:
            ex_order = torch.LongTensor(
                range(self.ex[pn][split][key].size(0)))
            if self.is_cuda:
                ex_order = ex_order.cuda()
            random.shuffle(ex_order)
            orders[key] = ex_order
            self.ex[pn][split][key] = \
                self.ex[pn][split][key].index_select(0, ex_order)
            self.sent[pn][split][key] = \
                self.sent[pn][split][key].index_select(0, ex_order)
            self.sent_lengths[pn][split][key] = \
                self.sent_lengths[pn][split][key].index_select(0, ex_order)
            self.ent[pn][split][key] = \
                self.ent[pn][split][key].index_select(0, ex_order)
            self.ent_init[pn][split][key] = \
                self.ent_init[pn][split][key].index_select(0, ex_order)
            for i in range(1, key[1]):
                self.ctx[pn][split][key][i] = \
                    self.ctx[pn][split][key][i].index_select(0, ex_order)
                self.ctx_lengths[pn][split][key][i] = \
                    self.ctx_lengths[pn][split][key][i].index_select(
                        0, ex_order)
                self.ent_labels[pn][split][key][i] = \
                    self.ent_labels[pn][split][key][i].index_select(
                        0, ex_order)
            self.ent_labels[pn][split][key][key[1]] = \
                self.ent_labels[pn][split][key][key[1]].index_select(
                    0, ex_order)
            self.ids[pn][split][key] = [self.ids[pn][split][key][i]
                                        for i in ex_order]
        return orders


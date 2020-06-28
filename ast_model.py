# -*- coding: utf-8 -*-
"""AST_Model.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1fh0TOreE_BOkd-z1FXakrdKk-HW5uLa3
"""

from google.colab import drive
drive.mount('/content/drive')

#pip install --upgrade tensorflow-gpu
#Hyperparameter tuning : https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams
#Dataframe ex : https://www.oreilly.com/library/view/introduction-to-machine/9781449369880/ch04.html
#Oversampling:  https://towardsdatascience.com/machine-learning-multiclass-classification-with-imbalanced-data-set-29f6a177c1a
#Test SMOTE : #https://github.com/SantiagoEG/ImbalancedMulticlass/blob/master/imblMulticlass.py
#https://www.ritchieng.com/machine-learning-evaluate-classification-model/
#https://matthewmcateer.me/blog/getting-started-with-attention-for-classification/
import tensorflow as tf
from tensorboard.plugins.hparams import api as hp
from imblearn.over_sampling import SMOTE
import time
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import keras
import numpy as np
import tensorflow_datasets as tfds
import tensorflow.keras.backend as K
from tensorflow.keras.layers import Input, Lambda, Dense
from tensorflow.keras.models import Model
from sklearn import preprocessing
from keras.preprocessing.text import Tokenizer
from tensorflow.keras.layers import Dense, Flatten, Dropout, Conv1D, Reshape, Concatenate
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from imblearn.over_sampling import SMOTE
from sklearn.utils import class_weight

data = pd.read_csv('/content/drive/My Drive/Issue_elasticsearch.csv',error_bad_lines=False, index_col=False, dtype='unicode',low_memory=False)
data = data.sample(frac=1)
data = data.fillna('unknown').groupby(['Name', 'FixedByID']).filter(lambda x: len(x) > 6)
#data.FixedByID.value_counts()
dev_y = list(data['FixedByID']) # Developer List
btype_y = list(data['Name'])  # Bug Type List


x_context = list(data['Title_Description'])
data.AST = data.AST.astype(str)
x_AST = list(data['AST'])

le = preprocessing.LabelEncoder()
le.fit_transform(btype_y)

noofdev = list(set(dev_y))
noofbugtype = list(set(btype_y))

def encode(le, labels):
    #enc = le.transform(labels)
    #return keras.utils.to_categorical(labels)
    #return enc
    return keras.utils.to_categorical(le.fit_transform(labels))

def decode(le, one_hot):
    #dec = np.argmax(one_hot, axis=1)
    dec = np.argmax(one_hot)
    return dec

dev_y_enc = encode(le, dev_y)
btype_y_enc = encode(le, btype_y)

#80% / 20% train / test split:
train_size = int(len(x_context) * .8)

np.argmax(keras.utils.to_categorical(le.fit_transform(dev_y)), axis=1)

x_train_context = x_context[:train_size]
x_train_AST = x_AST[:train_size]
dev_y_train = dev_y_enc[:train_size]
btype_y_train = btype_y_enc[:train_size]

x_test_context = x_context[train_size:]
x_test_AST = x_AST[train_size:]
dev_y_test = dev_y_enc[train_size:]
btype_y_test = btype_y_enc[train_size:]

# convert string to lower case 
x_train_context = [s.lower() for s in x_train_context]
x_test_context = [s.lower() for s in x_test_context]
#=======================Convert string to index================
# Tokenizer
tk_context = Tokenizer(num_words=None, char_level=None, oov_token='Unknown',filters='!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n')
tk_context.fit_on_texts(x_context)

tk_AST = Tokenizer(num_words=None, char_level=None, oov_token='Unknown')
tk_AST.fit_on_texts(x_AST)

# Convert string to index 
x_train_context_sequences = tk_context.texts_to_sequences(x_train_context)
x_train_AST_sequences = tk_context.texts_to_sequences(x_train_AST)
x_test_context_sequences = tk_AST.texts_to_sequences(x_test_context)
x_test_AST_sequences = tk_AST.texts_to_sequences(x_test_AST)

# Padding
x_train_context = pad_sequences(x_train_context_sequences, maxlen=500, padding='post')
x_train_AST = pad_sequences(x_train_AST_sequences, maxlen=500, padding='post')
x_test_context = pad_sequences(x_test_context_sequences, maxlen=500, padding='post')
x_test_AST = pad_sequences(x_test_AST_sequences, maxlen=500, padding='post')

# Convert to numpy array
x_train_context = np.array(x_train_context)
x_train_AST = np.array(x_train_AST)
x_test_context = np.array(x_test_context)
x_test_AST = np.array(x_test_AST)

print(btype_y_train.shape[1],btype_y_test.shape[1], dev_y_train.shape[1], dev_y_test.shape[1])

def get_angles(pos, i, d_model):
  angle_rates = 1 / np.power(10000, (2 * (i//2)) / np.float32(d_model))
  return pos * angle_rates
  
def positional_encoding(position, d_model):
  angle_rads = get_angles(np.arange(position)[:, np.newaxis],
                          np.arange(d_model)[np.newaxis, :],
                          d_model)
  
  # apply sin to even indices in the array; 2i
  angle_rads[:, 0::2] = np.sin(angle_rads[:, 0::2])
  
  # apply cos to odd indices in the array; 2i+1
  angle_rads[:, 1::2] = np.cos(angle_rads[:, 1::2])
    
  pos_encoding = angle_rads[np.newaxis, ...]
    
  return tf.cast(pos_encoding, dtype=tf.float32)

def point_wise_feed_forward_network(d_model, dff):
  return tf.keras.Sequential([
      tf.keras.layers.Dense(dff, activation='relu'),  # (batch_size, seq_len, dff)
      tf.keras.layers.Dense(d_model)  # (batch_size, seq_len, d_model)
  ])

def scaled_dot_product_attention(q, k, v, mask):
  """Calculate the attention weights.
  q, k, v must have matching leading dimensions.
  k, v must have matching penultimate dimension, i.e.: seq_len_k = seq_len_v.
  The mask has different shapes depending on its type(padding or look ahead) 
  but it must be broadcastable for addition.
  
  Args:
    q: query shape == (..., seq_len_q, depth)
    k: key shape == (..., seq_len_k, depth)
    v: value shape == (..., seq_len_v, depth_v)
    mask: Float tensor with shape broadcastable 
          to (..., seq_len_q, seq_len_k). Defaults to None.
    
  Returns:
    output, attention_weights
  """

  matmul_qk = tf.matmul(q, k, transpose_b=True)  # (..., seq_len_q, seq_len_k)
  
  # scale matmul_qk
  dk = tf.cast(tf.shape(k)[-1], tf.float32)
  scaled_attention_logits = matmul_qk / tf.math.sqrt(dk)

  # add the mask to the scaled tensor.
  if mask is not None:
    scaled_attention_logits += (mask * -1e9)  

  # softmax is normalized on the last axis (seq_len_k) so that the scores
  # add up to 1.
  attention_weights = tf.nn.softmax(scaled_attention_logits, axis=-1)  # (..., seq_len_q, seq_len_k)

  output = tf.matmul(attention_weights, v)  # (..., seq_len_q, depth_v)

  return output, attention_weights

def create_padding_mask(seq):
  seq = tf.cast(tf.math.equal(seq, 0), tf.float32)
  
  # add extra dimensions to add the padding
  # to the attention logits.
  return seq[:, tf.newaxis, tf.newaxis, :]  # (batch_size, 1, 1, seq_len)
  
def create_masks(inp):
    # Encoder padding mask
    enc_padding_mask = create_padding_mask(inp)

    return enc_padding_mask

def TransformerEncoder(x, contextflag):   
   if contextflag == True:
     ##################Initalize Context Variable###################
     input_vocab_size = len(tk_context.word_index) + 2
     target_vocab_size = len(tk_context.word_index) + 2
     enc_padding_mask = create_masks(x)
     tranformer = Transformer(num_layers, d_model, num_heads, dff,
                          len(tk_context.word_index) + 1, len(tk_context.word_index) + 1, dropout_rate)
     t_out = tranformer(x, True,enc_padding_mask)
   else:
     input_vocab_size = len(tk_AST.word_index) + 2
     target_vocab_size = len(tk_AST.word_index) + 2
     enc_padding_mask = create_masks(x)
     tranformer = Transformer(num_layers, d_model, num_heads, dff,
                          len(tk_AST.word_index) + 1, len(tk_AST.word_index) + 1, dropout_rate)
     t_out = tranformer(x, True,enc_padding_mask)

   return t_out

def codeembedding(x): 
    embedsize = len(tk_context.word_index) + 1
    result=  tf.keras.layers.Embedding(embedsize, output_dim=d_model)(x)
    return result

def oversampling(x, y): 
   #smote = SMOTE('minority',random_state=42)
   smote = SMOTE('minority',k_neighbors=2)
   osx, osy = smote.fit_sample(x, y)
   return osx, osy

def calculateclassWeights(y):
   classweights = class_weight.compute_class_weight('balanced', np.unique(y), y)
   return classweights

class MultiHeadAttention(tf.keras.layers.Layer):
  def __init__(self, d_model, num_heads):
    super(MultiHeadAttention, self).__init__()
    self.num_heads = num_heads
    self.d_model = d_model
    
    assert d_model % self.num_heads == 0
    
    self.depth = d_model // self.num_heads
    
    self.wq = tf.keras.layers.Dense(d_model)
    self.wk = tf.keras.layers.Dense(d_model)
    self.wv = tf.keras.layers.Dense(d_model)
    
    self.dense = tf.keras.layers.Dense(d_model)
        
  def split_heads(self, x, batch_size):
    """Split the last dimension into (num_heads, depth).
    Transpose the result such that the shape is (batch_size, num_heads, seq_len, depth)
    """
    x = tf.reshape(x, (batch_size, -1, self.num_heads, self.depth))
    return tf.transpose(x, perm=[0, 2, 1, 3])
    
  def call(self, v, k, q, mask):
    batch_size = tf.shape(q)[0]
    q = self.wq(q)  # (batch_size, seq_len, d_model)
    k = self.wk(k)  # (batch_size, seq_len, d_model)
    v = self.wv(v)  # (batch_size, seq_len, d_model)
    
    q = self.split_heads(q, batch_size)  # (batch_size, num_heads, seq_len_q, depth)
    k = self.split_heads(k, batch_size)  # (batch_size, num_heads, seq_len_k, depth)
    v = self.split_heads(v, batch_size)  # (batch_size, num_heads, seq_len_v, depth)
    
    # scaled_attention.shape == (batch_size, num_heads, seq_len_q, depth)
    # attention_weights.shape == (batch_size, num_heads, seq_len_q, seq_len_k)
    scaled_attention, attention_weights = scaled_dot_product_attention(
        q, k, v, mask)
    
    scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])  # (batch_size, seq_len_q, num_heads, depth)

    concat_attention = tf.reshape(scaled_attention, 
                                  (batch_size, -1, self.d_model))  # (batch_size, seq_len_q, d_model)

    output = self.dense(concat_attention)  # (batch_size, seq_len_q, d_model)
        
    return output, attention_weights

class EncoderLayer(tf.keras.layers.Layer):
  def __init__(self, d_model, num_heads, dff, rate=0.001):
    super(EncoderLayer, self).__init__()

    self.mha = MultiHeadAttention(d_model, num_heads)
    self.ffn = point_wise_feed_forward_network(d_model, dff)

    self.layernorm1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
    self.layernorm2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)
    
    self.dropout1 = tf.keras.layers.Dropout(rate)
    self.dropout2 = tf.keras.layers.Dropout(rate)
    
  def call(self, x, training, mask):

    attn_output, _ = self.mha(x, x, x, mask)  # (batch_size, input_seq_len, d_model)
    attn_output = self.dropout1(attn_output, training=training)
    out1 = self.layernorm1(x + attn_output)  # (batch_size, input_seq_len, d_model)
    
    ffn_output = self.ffn(out1)  # (batch_size, input_seq_len, d_model)
    ffn_output = self.dropout2(ffn_output, training=training)
    out2 = self.layernorm2(out1 + ffn_output)  # (batch_size, input_seq_len, d_model)    
    return out2

class Encoder(tf.keras.layers.Layer):
  def __init__(self, num_layers, d_model, num_heads, dff, input_vocab_size,
               maximum_position_encoding, rate=0.1):
    super(Encoder, self).__init__()

    self.d_model = d_model
    self.num_layers = num_layers
    
    self.embedding = tf.keras.layers.Embedding(input_vocab_size, d_model)
    self.pos_encoding = positional_encoding(maximum_position_encoding, 
                                            self.d_model)   
    
    self.enc_layers = [EncoderLayer(d_model, num_heads, dff, rate) 
                       for _ in range(num_layers)]
  
    self.dropout = tf.keras.layers.Dropout(rate)
        
  def call(self, x, training, mask):

    seq_len = tf.shape(x)[1]

    # adding embedding and position encoding.
    x = self.embedding(x)  # (batch_size, input_seq_len, d_model)
    x *= tf.math.sqrt(tf.cast(self.d_model, tf.float32))
    x += self.pos_encoding[:, :seq_len, :]

    x = self.dropout(x, training=training)
    
    for i in range(self.num_layers):
      x = self.enc_layers[i](x, training, mask)
    
    return x  # (batch_size, input_seq_len, d_model)

class Transformer(tf.keras.Model):
    def __init__(self, num_layers, d_model, num_heads, dff, input_vocab_size, 
                   target_vocab_size, rate=0.1):
        super(Transformer, self).__init__()

        self.encoder = Encoder(num_layers, d_model, num_heads, dff, 
                               input_vocab_size, rate)

        self.dense = tf.keras.layers.Dense(d_model, activation='relu')
        self.dropout = tf.keras.layers.Dropout(rate)
        self.final_layer = tf.keras.layers.Dense(256, activation='relu')

    def call(self, inp, training, enc_padding_mask):
        enc_output = self.encoder(inp, training, enc_padding_mask)
        enc_output = self.dense(enc_output[:,0])
        enc_output = self.dropout(enc_output, training=training)
        final_output = self.final_layer(enc_output)
        return final_output
class CustomSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
    def __init__(self, d_model, warmup_steps=4000):
        super(CustomSchedule, self).__init__()

        self.d_model = d_model
        self.d_model = tf.cast(self.d_model, tf.float32)

        self.warmup_steps = warmup_steps

    def __call__(self, step):
        arg1 = tf.math.rsqrt(step)
        arg2 = step * (self.warmup_steps ** -1.5)

        return tf.math.rsqrt(self.d_model) * tf.math.minimum(arg1, arg2)

###########################Initalize Variable#####################################
num_layers = 6
d_model = 512
dff = 2048
num_heads = 8

dropout_rate = 0.5
learning_rate = CustomSchedule(d_model)
optimizer = tf.keras.optimizers.Adam(learning_rate)

# Commented out IPython magic to ensure Python compatibility.
len(X_sm_train_AST)
# %load_ext tensorboard

btype_y_train.shape[1]

######## RUN With Create OverSampling #######
X_sm_train_context, Btype_sm_y_train  = oversampling(x_train_context, btype_y_train)
X_sm_train_AST, Btype_sm_y_train = oversampling(x_train_AST, btype_y_train)

X_sm_train_context, Dev_sm_y_train = oversampling(x_train_context, dev_y_train)
X_sm_train_AST, Dev_sm_y_train = oversampling(x_train_AST, dev_y_train)

# inputs
input_context = Input(shape=(500,), dtype=tf.float32, name="Bug_TitleandDescription") #Bug Title and Description 
input_AST = Input(shape=(500,), dtype=tf.float32, name ="Bug_CodeSnippetAST") #Bug Code Snippet AST

# Bug Title and Description Embedding Layer
contextmodel = Model(inputs=input_context, outputs=TransformerEncoder(input_context,True))

# Bug Code Snippet AST Embedding Layer
codedense = tf.keras.layers.Dense(256, activation='relu')(codeembedding(input_AST))
LSTM = tf.keras.layers.LSTM(128)(codedense)
codemodel = Model(inputs=input_AST, outputs=LSTM)

#attention on both output
#contextmodel_Dense = Dense(128, activation="relu",name="contextmodel_Dense")(contextmodel.output)
#combinedInput_att= tf.keras.layers.Attention(name="attention")([contextmodel_Dense,codemodel.output])

# the Context and AST Embedding concatenation Layer
combinedInput = tf.keras.layers.Concatenate(name="concatenate")([contextmodel.output, codemodel.output])

# Combine Input and Attention
#combinedInputandAttention = tf.keras.layers.Concatenate(name="concatenate_attention")([combinedInput_att, combinedInput])

dropout = Dropout(0.5)(combinedInput)
final_btype_output = Dense(Btype_sm_y_train.shape[1], activation="softmax", name="Bug_Type")(dropout)
final_dev_output = Dense(Dev_sm_y_train.shape[1], activation="softmax",name="Developer")(dropout)
model = Model(inputs=[contextmodel.input, codemodel.input], outputs=[final_btype_output, final_dev_output])


METRICS = [
	keras.metrics.TruePositives(name='tp'),
	keras.metrics.FalsePositives(name='fp'),
	keras.metrics.TrueNegatives(name='tn'),
	keras.metrics.FalseNegatives(name='fn'),
	keras.metrics.BinaryAccuracy(name='accuracy'),
	keras.metrics.Precision(name='precision'),
	keras.metrics.Recall(name='recall'),
	keras.metrics.AUC(name='auc'),
] 

model.compile(optimizer=optimizer,
              loss='categorical_crossentropy',
              metrics=METRICS)


#Visualize Model
logdir = "logs/"
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=logdir)
#A model.fit() training loop will check at end of every epoch whether the loss is no longer decreasing, considering the min_delta and patiencez
earlystop = tf.keras.callbacks.EarlyStopping(monitor='loss', patience=3)

history = model.fit([X_sm_train_context,X_sm_train_AST], 
          [Btype_sm_y_train, Dev_sm_y_train], 
          callbacks=[tensorboard_callback,earlystop],
          epochs=3, verbose=2, validation_split= 0.1)

tf.keras.utils.plot_model(
    model, to_file='model.png', show_shapes=False, show_layer_names=True,
    rankdir='TB', expand_nested=False, dpi=96
)

# Commented out IPython magic to ensure Python compatibility.
y_pred = model.predict([x_test_context, x_test_AST])

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (classification_report,
							 confusion_matrix,
							 roc_auc_score)
# %matplotlib inline
# %config InlineBackend.figure_format = 'retina'
  
report = classification_report([btype_y_test,dev_y_test], y_pred)
print(report)

y_pred
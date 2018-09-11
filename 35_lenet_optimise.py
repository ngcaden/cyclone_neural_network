"""
    This programme implements simple LeNet CNN on training to regress
    hurricane centre position.

    Script should be run as followed:

    'python 11_lenet.py input output option'

    + input: name of input data file
    + output: name of output log file
    + option: special option to perform on the data
        * normalisation
        * augmentation
"""

from __future__ import print_function
import keras
from keras.preprocessing.image import ImageDataGenerator
from keras.models import Sequential
from keras.layers import Dense, Dropout, Activation, Flatten
from keras.layers import Conv2D, MaxPooling2D
from keras.wrappers.scikit_learn import KerasRegressor
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from keras.utils import plot_model
import os
import pickle
import cv2
import numpy as np
from numpy import reshape
import random
from augmentation import augment
from hyperas.distributions import normal, choice
from hyperas import optim
from hyperopt import Trials, STATUS_OK, tpe
import copy

os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"   # see issue #152
os.environ["CUDA_VISIBLE_DEVICES"]="0"




# Hyper-parameters



# Set up network training instance
def create_model(x_train, y_train, x_test, y_test):
    BATCH_SIZE = 64
    EPOCHS = 25
    RESIZE_DIM = 256
    RANDOM_CROP_DIM = 224
    NO_FILTERS = [16,32,64]

    history = None

    model = Sequential()

    f1 = {{choice(NO_FILTERS)}}
    f2 = {{choice(NO_FILTERS)}}

    model.add(Conv2D(f1, (3, 3), padding='same',
                        input_shape=(RANDOM_CROP_DIM,RANDOM_CROP_DIM,1)))
    model.add(Activation('relu'))
    model.add(Conv2D(f1, (3, 3), padding='same'))
    model.add(Activation('relu'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=(2,2)))
    model.add(Dropout(0.25))

    model.add(Conv2D(f2, (3, 3), padding='same'))
    model.add(Activation('relu'))
    model.add(Conv2D(f2, (3, 3), padding='same'))
    model.add(Activation('relu'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=(2,2)))
    model.add(Dropout(0.25))

    model.add(Flatten())
    model.add(Dense(500))
    model.add(Activation('relu'))
    model.add(Dropout(0.5))
    model.add(Dense(2, kernel_initializer='normal'))
    model.add(Activation('linear'))

    opt = keras.optimizers.rmsprop(lr=0.0001, decay=1e-6)

    model.compile(loss='mean_squared_error', optimizer=opt)

    class customValidationCallback(keras.callbacks.Callback):
        def __init__(self,tr_params):
            self.tr_params  = tr_params
        def on_train_begin(self, logs={}, min_delta=0, patience=3):
            self.losses = []
            self.val_error_means = []
            self.val_error_stds = []
            self.min_delta = min_delta
            self.patience = patience
            self.patience_left = patience

        def on_epoch_end(self, epoch, logs={}):
            self.losses.append(logs.get('loss'))
            prediction = self.model.predict(self.validation_data[0])
            val_error = np.abs(self.validation_data[1] - prediction)
            val_error = np.sqrt(np.dot(val_error**2, np.array([1,1])))
            current_error = np.mean(val_error)

            if len(self.val_error_means) > 0:
                delta = current_error - self.val_error_means[self.patience_left-4]
                if delta > self.min_delta:
                    self.patience_left -= 1
                    if self.patience_left == 0:
                        self.model.stop_training = True

                else:
                    # Reset patience_left if there is a decrease
                    self.patience_left = self.patience

            self.val_error_means.append(current_error)
            self.val_error_stds.append(np.std(val_error))
            with open('lenet_params_search.txt','a') as f:
                f.write(str(self.tr_params) + ',' + str(self.val_error_means) + ',' + str(self.val_error_stds) + '\n')

    # Train the CNN
    history = customValidationCallback(tr_params=[f1,f2])

    model.fit(x_train, y_train,
        epochs=EPOCHS, batch_size=BATCH_SIZE,
        validation_data = (x_test, y_test),
        callbacks = [history]
    )

    return {'loss': np.min(history.val_error_means),
            'status': STATUS_OK,
            'history':{'loss':history.losses,
                       'val_e_mean': history.val_error_means,
                       'val_e_std': history.val_error_stds,
                       # 'best_model': history.best_model
                      },
            'model': None
            }

# Prepare data for training
def data():
    TRAIN_DATA = '/vol/bitbucket/qn14/train_raw_data.p'
    VAL_DATA = '/vol/bitbucket/qn14/validate_raw_data.p'
    RANDOM_CROP_NUMBER = 2
    RESIZE_DIM = 256
    RANDOM_CROP_DIM = 224
    NO_FILTERS = [16,32,64]


    [x_train,y_train] = pickle.load(open(TRAIN_DATA, 'rb'))
    [x_test,y_test] = pickle.load(open(VAL_DATA, 'rb'))
    x_train = np.array([cv2.cvtColor(item, cv2.COLOR_BGR2GRAY) for item in x_train])
    x_test = np.array([cv2.cvtColor(item, cv2.COLOR_BGR2GRAY) for item in x_test])
    x_train = x_train.reshape(x_train.shape + (1,))
    x_test = x_test.reshape(x_test.shape + (1,))
    y_train = np.array([item[0] for item in y_train])
    y_test = np.array([item[0] for item in y_test])

    x_train, y_train, x_test, y_test = augment(x_train,
        y_train, x_test, y_test, ['all'],
        RANDOM_CROP_NUMBER, RESIZE_DIM, RANDOM_CROP_DIM)

    # Normalise input
    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    y_train = y_train.astype('float32')
    # Normalise output
    y_test = y_test.astype('float32')
    y_train /= 255
    y_test /= 255

    return x_train, y_train, x_test, y_test


# Main function
def main(args):
    MODEL_NAME = args[0]
    SAVE_DIR = '/vol/bitbucket/qn14/'
    NO_FILTERS = [16,32,64]

    trials = Trials()
    best_run, best_model = optim.minimize(model=create_model,
                                          data=data,
                                          algo=tpe.suggest,
                                          max_evals=10,
                                          trials=trials)
    print("Best performing model chosen hyper-parameters:")
    print(best_run)

    results = copy.deepcopy(trials.trials)
    pickle.dump(results, open(SAVE_DIR + MODEL_NAME + '.p', 'wb'))


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])


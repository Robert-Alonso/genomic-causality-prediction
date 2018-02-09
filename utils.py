import os
import random
import numpy as np
import pandas as pd

from sklearn.metrics import f1_score
from sklearn.metrics import accuracy_score
from sklearn.metrics import log_loss
from sklearn.metrics import confusion_matrix
from sklearn.metrics import roc_auc_score
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from imblearn.under_sampling import RandomUnderSampler

def filter_pvalue(df, pvalue_range):
    df = df[df['Pvalue'].apply(lambda x: x <= pvalue_range[0] or x >= pvalue_range[1])].copy()
    df['Target'] = df['Pvalue'].apply(lambda x: 1 if x < np.mean(pvalue_range) else 0)
    return df

def to_categorical(df, columns):
    for col in columns:
        df[col] = df[col].astype('category')
    return df

def load_fold(path, n_fold=0):
    folds = os.listdir(path)
    test_fold = folds[n_fold]
    print(f'Test fold: {test_fold}')
    test = pd.read_csv(f'{path}/{test_fold}', sep = ';')
    train = pd.DataFrame(columns = test.columns)
    for train_fold in [fold for fold in folds if fold != test_fold]:
        print(f'Train fold: {train_fold}')
        train = pd.concat((train, pd.read_csv(f'{path}/{train_fold}', sep = ';')))
    train = train.reset_index(drop=True)
    
    train = filter_pvalue(train, (0.01, 0.5))
    test = filter_pvalue(test, (0.01, 0.5))

    columns = ['CauseGene', 'EffectGene', 'Replicate', 'Treatment']
    train = to_categorical(train, columns)
    test = to_categorical(test, columns)

    train = train.reset_index(drop=True)
    test = test.reset_index(drop=True)

    return train, test, test_fold

def gmean_score(y, y_pred):
    matrix = confusion_matrix(y, y_pred)
    tn = matrix[0][0]
    tp = matrix[1][1]
    fn = matrix[1][0]
    fp = matrix[0][1]
    return np.sqrt(tp / (tp + fn) * tn / (tn + fp))    

def true_positive_rate(y, y_pred):
    matrix = confusion_matrix(y, y_pred)
    tn = matrix[0][0]
    tp = matrix[1][1]
    fn = matrix[1][0]
    fp = matrix[0][1]
    return tp / (tp + fn)

def true_negative_rate(y, y_pred):
    matrix = confusion_matrix(y, y_pred)
    tn = matrix[0][0]
    tp = matrix[1][1]
    fn = matrix[1][0]
    fp = matrix[0][1]
    return tn / (tn + fp)

def evaluate_metrics(y, y_pred, y_pred_proba, model='', fold='', desc=''):
    df = pd.DataFrame()
    df.loc[0, 'Model'] = model
    df.loc[0, 'Fold'] = fold
    df.loc[0, 'ROC-AUC'] = roc_auc_score(y, y_pred_proba)
    df.loc[0, 'G-mean'] = gmean_score(y, y_pred)
    df.loc[0, 'F1-Score'] = f1_score(y, y_pred)
    df.loc[0, 'TPR'] = true_positive_rate(y, y_pred)
    df.loc[0, 'TNR'] = true_negative_rate(y, y_pred)
    df.loc[0, 'Accuracy'] = accuracy_score(y, y_pred)
    df.loc[0, 'Precision'] = precision_score(y, y_pred)
    df.loc[0, 'Recall'] = recall_score(y, y_pred)    
    df.loc[0, 'Logloss'] = log_loss(y, y_pred_proba)
    df.loc[0, 'Description'] = desc
    print('Confusion matrix:')
    print(confusion_matrix(y, y_pred))
    print(df)
    return df

def train_model(model, train, test):
    model.fit(train[[col for col in train.columns \
            if 'cause' in col or 'effect' in col]], train['Target'])
    y_pred = model.predict(test[[col for col in test.columns \
            if 'cause' in col or 'effect' in col]])
    y_pred_proba = model.predict_proba(test[[col for col in test.columns \
            if 'cause' in col or 'effect' in col]])[:,1]
    return model, y_pred, y_pred_proba

def train_model_sample(model, X_train, y_train, test):
    model.fit(X_train, y_train)
    y_pred = model.predict(test[[col for col in test.columns \
            if 'cause' in col or 'effect' in col]])
    y_pred_proba = model.predict_proba(test[[col for col in test.columns \
            if 'cause' in col or 'effect' in col]])[:,1]
    return model, y_pred, y_pred_proba

def evaluate_classifier_sample(path, model, results, bags=10, desc=''):
    for i in range(len(os.listdir(path))):
        train, test, test_fold = load_fold(path, i)
        print('Evaluating...')

        X_train, y_train = train[[col for col in train.columns \
            if 'cause' in col or 'effect' in col]], train['Target']
        y_pred = np.zeros(len(test))
        y_pred_proba = np.zeros(len(test))
        for j in range(bags):
            print('Bag No:', j)
            rus = RandomUnderSampler(random_state=random.randint(1, 1e9))
            X_resampled, y_resampled = rus.fit_sample(X_train, y_train)
            model, y_pred_, y_pred_proba_ = train_model_sample(model, 
                                            X_resampled, y_resampled, test)
            y_pred += y_pred_
            y_pred_proba += y_pred_proba_          
        
        y_pred = [int(round(x/bags)) for x in y_pred]
        y_pred_proba /= bags

        model_name = str(model.__class__).split('.')[-1].replace('>','').replace("'",'')
        result = evaluate_metrics(test['Target'], y_pred, y_pred_proba, 
                         model_name, test_fold.split('.')[0], desc)

        results = pd.concat((results, result)) 

    results = results.reset_index(drop=True)
    return results

def evaluate_classifier(path, model, results, desc=''):
    for i in range(len(os.listdir(path))):
        train, test, test_fold = load_fold(path, i)
        print('Evaluating...')

        model, y_pred, y_pred_proba = train_model(model, train, test)

        model_name = str(model.__class__).split('.')[-1].replace('>','').replace("'",'')
        result = evaluate_metrics(test['Target'], y_pred, y_pred_proba, 
                         model_name, test_fold.split('.')[0], desc)

        results = pd.concat((results, result)) 

    results = results.reset_index(drop=True)
    return results

################# DATA PREPROCESSING #####################

def outer_product(df):
    df_cause = df[[col for col in df.columns if 'cause' in col]]
    df_effect = df[[col for col in df.columns if 'effect' in col]]
    df_columns = [f'outer-c{i+1:02}-e{j+1:02}' for i in range(df_cause.shape[1]) \
                                           for j in range(df_effect.shape[1])]
    df_data = np.array([np.outer(cause, effect) for cause, effect in \
                            zip(df_cause.values, df_effect.values)])
    df_data = np.reshape(df_data, (-1, df_cause.shape[1] * df_effect.shape[1]))
    df_data = pd.DataFrame(df_data, columns=df_columns)
    df = df[[col for col in df.columns \
                if 'cause' not in col and 'effect' not in col]]
    return pd.concat((df, df_data), 1)   
    
def group_wise_data(df):
    y = df['Target'].values
    y = np.reshape(y, (-1, 6))
    X = df[[col for col in df.columns if 'outer' in col]].values
    X = np.reshape(X, (-1, 6, X.shape[1]))
    return X, y   

def get_random_batch(X, y, sampler):
    '''
    Input / Output shapes
    X: (#elements, #treatments, #variables)
    y: (#elements, #treatments)
    '''
    X_reshaped = np.reshape(X, (-1, np.prod(X.shape[1:])))
    y_reshaped = np.array([np.prod(v) for v in y]) 
    X_resampled, y_resampled = sampler.fit_sample(X_reshaped, y_reshaped)
    X_resampled = np.reshape(X_resampled, (-1, X.shape[1], X.shape[2]))
    y_resampled = np.array([[v] * X.shape[1] for v in y_resampled])
    return X_resampled, y_resampled    

# TODO: use sklearn train_test_split
def train_val_split(X, y, val_size):
    '''
    Input / Output shapes
    X: (#elements, #treatments, #variables)
    y: (#elements, #treatments)
    '''
    merged = np.concatenate((X, y.reshape(-1, X.shape[1], 1)), 2)
    np.random.shuffle(merged)
    X, y = merged[:,:,:-1], merged[:,:,-1].reshape(-1, X.shape[1])
    return X[:-val_size], X[-val_size:], y[:-val_size], y[-val_size:]

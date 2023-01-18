# Dependencies
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import numpy as np
import pandas as pd
from datetime import datetime as dt
from dateutil import parser



default_args = {
    'owner' : "Text-Mining_Project",
    
    # Lancer le DAG chaque jour
    'start_date' : datetime(2023, 1, 17),
    'depends_on_past' : False,

    # Si jamais l'éxecution fail, retenter 1 fois au bout de 5 minutes
    'retries' : 1,
    'retry_delay' : timedelta(minutes=5)
}


class MyDag(DAG):
    def __init__(self, *args, **kwargs):
        conn = psycopg2.connect(user = "m140",password = "m140",host = "db-etu.univ-lyon2.fr",port = "5432",database = "m140")
        try:
            cur = conn.cursor()
            history = "SELECT * FROM history"
            cur.execute(history)
            self.df = pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])
        except : 
            print ("Erreur lors de la récupération de la table PostgreSQL")
        super(MyDag, self).__init__(*args, **kwargs)


def clean_date_ajout(**kwargs):
    df = kwargs['dag_run'].dag.df
    
    df_moisreview=df['date_review'].map(str)
    for i in range(df.shape[0]):
        df_moisreview[i]=df_moisreview[i].split()[4]
    df_moisreservation=df['reservation_date'].map(str)
    for i in range(df.shape[0]):
        df_moisreservation[i]=df_moisreservation[i].split()[0].lower()
        df_anneereservation=df['reservation_date'].map(str)
    for i in range(df.shape[0]):
        df_anneereservation[i]=df_anneereservation[i].split()[1]
        from time import strptime
    import locale
    locale.setlocale(locale.LC_TIME,'')

    list_mois_num = [strptime(moisreservation,'%B').tm_mon for moisreservation in df_moisreservation]
    list_mois_com = [strptime(moisreview,'%B').tm_mon for moisreview in df_moisreview]
    delai = [com - num if com-num>-1 else 12+(com-num) for com, num in zip(list_mois_com, list_mois_num)]

    d = {'month_str': df_moisreservation, 'month_num': list_mois_num, 'year' : df_anneereservation,  'delay_comment': delai}
    df_date = pd.DataFrame(data=d)
    df = pd.concat([df,df_date], join = 'outer', axis = 1)

    


def ajout_levels(**kwargs):
    df = kwargs['dag_run'].dag.df

    conditionlist_note = [
    (df['grade_review'] >= 8) ,
    (df['grade_review'] > 5) & (df['grade_review'] <8),
    (df['grade_review'] <= 5)]
    choicelist_note = [2,1,0]
    df['level_grade_review'] = np.select(conditionlist_note, choicelist_note, default='Not Specified')
    conditionlist_hotel = [
    (df['hotel'] == "Newport_Bay_Club"),
    (df['hotel'] == "New_York"),
    (df['hotel'] == "Sequoia_Lodge"),
    (df['hotel'] == "Cheyenne"),
    (df['hotel'] == "Santa_Fe"),
    (df['hotel'] == "Davy_Crockett_Ranch")
    ]
    choicelist_hotel = [6,5,4,3,2,1]
    df['level_hotel'] = np.select(conditionlist_hotel, choicelist_hotel, default='Not Specified')
    
    kwargs['dag_run'].dag.df = df


def recodage_type(**kwargs):
    df = kwargs['dag_run'].dag.df
    for i in ['grade_review']:
        df[i] = df[i].str.replace(",",".")
        df[i] = pd.to_numeric(df[i], downcast="float")

    df['level_hotel'] = df['level_hotel'].astype(int)
    df['level_grade_review'] = df['level_grade_review'].astype(int)
    
    kwargs['dag_run'].dag.df = df


def add_date(**kwargs) :
    df = kwargs['dag_run'].dag.df
    df = df.drop_duplicates(keep='first')
    df.drop(df[(df.delay_comment >3)].index , inplace=True)
    df=df.reset_index(drop=True)
    df_date=df['date_review'].map(str)
    for i in range(df.shape[0]):
        pos=df_date[i].find('le')
        #extraction
        df_date[i] = df_date[i][pos+2:] 
    df['date_review']=df_date
    df["date"] = pd.to_datetime(dict(year=df.year, month=df.month_num, day=1))
    df_clean = df.copy()

    kwargs['dag_run'].dag.df_clean = df_clean

def save_clean_file(**kwargs):
    df_clean = kwargs['dag_run'].dag.df_clean

    try:
        conn = psycopg2.connect(
            user = "m140",
            password = "m140",
            host = "db-etu.univ-lyon2.fr",
            port = "5432",
            database = "m140"
        )

        sql_create_historyclean = '''CREATE TABLE IF NOT EXISTS historyclean(
                Names TEXT
                Country TEXT,
                room_type TEXT,
                nuitee INT,
                reservation_date TEXT,
                traveler_infos TEXT,
                date_review TEXT,
                review_title TEXT,
                grade_review TEXT,
                positive_review TEXT,
                negative_review TEXT,
                usefulness_review INT,
                UniqueID TEXT,
                hotel TEXT,
                level_grade_review INT,
                level_hotel INT,
                month_str TEXT, 
                month_num INT,
                year INT,
                delay_comment INT,
                date DATE,
                ); '''

        fct.execute_req(conn, sql_create_historyclean)
        fct.insert_values(conn, df_clean, 'historyclean')

    except : 
        print ("Erreur lors de la récupération de la table PostgreSQL")
        df_clean.to_csv(str(path)+"df_clean.csv", sep=';', index=False, encoding="utf-8-sig")



dag = MyDAG(
    'dw',
    default_args = default_args,
    # Executer tous les jours à minuit
    schedule_interval = '0 0 * * *' # on peut le modifier par timedelta(hours=1) si on veut faire des tests chaque heure
)


# Tâche Airflow    
clean_date_ajout_task = PythonOperator(
    task_id = 'clean_date_ajout',
    python_callable = clean_date_ajout,
    dag = dag)

ajout_levels_task = PythonOperator(
    task_id = 'ajout_levels',
    python_callable = ajout_levels,
    dag = dag)

recodage_type_task = PythonOperator(
    task_id = 'recodage_type',
    python_callable = recodage_type,
    dag = dag)

add_date_task = PythonOperator(
    task_id = 'add_date',
    python_callable = add_date,
    dag = dag)

save_clean_file_task = PythonOperator(
    task_id = 'save_clean_file',
    python_callable = save_clean_file,
    dag = dag)

clean_date_ajout_task >> ajout_levels_task >> recodage_type_task >> add_date_task >> save_clean_file

execute_scrapping_dag >> clean_dag 
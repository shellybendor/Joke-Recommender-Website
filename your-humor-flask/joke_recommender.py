import random
import pickle
import numpy as np 
import pandas as pd
import matplotlib.pyplot as plt
from matrix_factorization import KernelMF, train_update_test_split
from sklearn.metrics import mean_squared_error
import seaborn as sns


class JokeRecommender:
    NOT_RATED = 99

    def __init__(self, current_ratings_from_sql):
        print("STARTING INIT")
        self._jokes_df = pd.read_csv("all_jokes.csv")
        self._num_jokes = self._jokes_df.shape[0]
        self._all_jokes = set([f"joke_{i}" for i in range(1, self._num_jokes + 1)])
        self._mf = pickle.load(open('model.pkl', 'rb'))  # loading the model
        if not current_ratings_from_sql.empty:
            self._mf.update_users(
                current_ratings_from_sql[["user_id", "item_id"]], current_ratings_from_sql["rating"], lr=0.001, n_epochs=20, verbose=0
            )
        print("DONE INIT")

    def _save_content_matrix(self):
        '''Reads words found in at least 4 jokes from a csv and creates a rating dataframe
        for the jokes as 'virtual users'
        '''
        common_words = pd.read_csv("common_words_in_jokes.csv")
        content_ratings = pd.DataFrame(columns=["user_id", "item_id", "rating"])
        for word in common_words["word"]:
            for joke_num in range(self._num_jokes):
                if word in self._jokes_df["jokes"][joke_num].lower():
                    content_ratings.loc[len(content_ratings)] = np.array([word, f"joke_{joke_num + 1}", 10])
        return content_ratings

    def _get_random_new_joke(self, user: str, ratings_df):
        '''Finds a joke not yet rated by the user.
        Returns the joke ID and the joke.
        '''
        unheard_jokes = self._all_jokes
        if not ratings_df.empty:
            items_known = ratings_df.query("user_id == @user")["item_id"]
            unheard_jokes = unheard_jokes - set(items_known)
        joke_id = random.choice(list(unheard_jokes))
        joke_num = int(joke_id.replace("joke_", "")) -1
        return joke_id, self._jokes_df["jokes"][joke_num]

    def _get_recommended_joke(self, user: str, ratings_df: pd.DataFrame):
        '''Retrains the model with the rating data of the user and finds the most recommended joke
        for them.
        Returns the joke ID and the joke.
        '''
        user_ratings = ratings_df[ratings_df["user_id"] == user]
        self._mf.update_users(
            user_ratings[["user_id", "item_id"]], user_ratings["rating"], lr=0.001, n_epochs=20, verbose=0
        )
        items_known = user_ratings["item_id"]
        best = self._mf.recommend(user=user, items_known=items_known, amount=1, include_user=False)
        joke_id = best["item_id"].item()
        joke_num = int(joke_id.replace("joke_", "")) -1
        return joke_id, self._jokes_df["jokes"][joke_num]

    def get_joke(self, user_name: str, added_ratings: pd.DataFrame):
        '''Given a dataframe of the new ratings of all users and a user name, returns a joke for the user to rate.
        If the user has rated less than 10 joke, the joke is random, otherwise it is recommended.
        '''
        num_jokes_rated = 0
        if not added_ratings.empty:
            added_ratings = added_ratings.rename(columns={'user_name': 'user_id'})
            added_ratings = added_ratings.astype({"rating": np.float32})
            num_jokes_rated = (added_ratings.user_id == user_name).sum()
        if num_jokes_rated < 10:
            print("Getting random joke")
            return self._get_random_new_joke(user_name, added_ratings)
        else:
            print("Getting recommended joke")
            return self._get_recommended_joke(user_name, added_ratings)

    def evaluate_model(self, with_content=False):
        """Evaluates the models perfomance by splitting into a test set and a training set.

        Args:
            with_content (bool, optional): Should model by evaluated with the jokes content taken into account.
                Defaults to False.
        """
        ratings_df = pd.read_csv("ratings_matrix.csv").astype({"rating": np.float32})
        counts = ratings_df["user_id"].value_counts()
        eval_data = ratings_df[ratings_df.user_id.isin(counts.index[counts.gt(1)])]
        # Splitting data into existing user ratings for training, new user's ratings for training, and new user's ratings for testing.
        (
            X_train_initial,
            y_train_initial,
            X_train_update,
            y_train_update,
            X_test_update,
            y_test_update,
        ) = train_update_test_split(eval_data, frac_new_users=0.2)

        if with_content:
            content_ratings = self._save_content_matrix()
            X_train_initial = pd.concat([X_train_initial, content_ratings[["user_id", "item_id"]]], ignore_index=True)
            y_train_initial = pd.concat([y_train_initial, content_ratings["rating"]], ignore_index=True).astype(np.float32)

        # Initial training
        matrix_fact = KernelMF(n_epochs=20, n_factors=40, verbose=1, lr=0.001, reg=0.005, min_rating=-10, max_rating=10)
        matrix_fact.fit(X_train_initial, y_train_initial)

        # Update model with new users
        matrix_fact.update_users(
            X_train_update, y_train_update, lr=0.001, n_epochs=20, verbose=1
        )

        # Test model on predictions for "new" users
        pred = matrix_fact.predict(X_test_update)

        # Create scatter plot of predictions
        x = y_test_update.head(200)
        y = pred[:200]
        sns.regplot(x=x, y=y)
        plt.plot([-10, 10], [-10, 10], '-')
        plt.title('Scatter plot of 200 predictions')
        plt.xlabel('Test set ratings')
        plt.ylabel('Test set predicted ratings')
        plt.show()

        rmse = mean_squared_error(y_test_update, pred, squared=False)
        norm_rmse = rmse / 20
        print(f"\nTest RMSE: {rmse:.4f}")
        print(f"\nTest Normalized RMSE: {norm_rmse:.4f}")


# THE FOLLOWING CODE IS USED ON MY LOCAL COMPUTER TO EVALUATE THE MODEL'S PREFORMANCE
# recommender = JokeRecommender(pd.DataFrame())
# print("Evaluating Model without content data")
# recommender.evaluate_model()
# print("Evaluating Model with content data")
# recommender.evaluate_model(with_content=True)

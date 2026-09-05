export type UserSession = {
  user: {
    user_id: string;
    email: string;
    name: string;
    roles: string[];
  };
};

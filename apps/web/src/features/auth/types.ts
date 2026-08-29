export type UserSession = {
  access_token: string;
  refresh_token?: string;
  user: {
    user_id: string;
    email: string;
    name: string;
    roles: string[];
  };
};

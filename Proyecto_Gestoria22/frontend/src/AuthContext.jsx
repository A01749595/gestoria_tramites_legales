import { createContext, useState, useContext, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(localStorage.getItem("token") || null);

    const login = (userToken) => {
    setToken(userToken);
    localStorage.setItem("token", userToken);
    };

    const logout = () => {
    setToken(null);
    localStorage.removeItem("token");
    };

    return (
    <AuthContext.Provider value={{ token, login, logout }}>
        {children}
    </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
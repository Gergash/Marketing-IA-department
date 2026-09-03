import { createContext, useContext } from "react";

const NavContext = createContext({ navigate: () => {}, path: "/" });

export function RouterProvider({ path, navigate, children }) {
  return <NavContext.Provider value={{ path, navigate }}>{children}</NavContext.Provider>;
}

export function useNavigate() {
  return useContext(NavContext).navigate;
}

export function usePath() {
  return useContext(NavContext).path;
}

export function Link({ to, className, children, ...rest }) {
  const navigate = useNavigate();
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
      {...rest}
    >
      {children}
    </a>
  );
}
